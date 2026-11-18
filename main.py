import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from datetime import datetime, timezone
from io import BytesIO
import hashlib
import sqlite3
import uuid

try:
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas
except ImportError:
    raise SystemExit(
        "Dependências ausentes. Execute: pip install -r requirements.txt"
    )

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "assinaturas.db"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def conectar():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def inicializar_banco():
    with conectar() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS assinaturas (
                id TEXT PRIMARY KEY,
                assinante TEXT NOT NULL,
                arquivo_original TEXT NOT NULL,
                hash_original TEXT NOT NULL,
                hash_assinado TEXT NOT NULL,
                pagina INTEGER NOT NULL,
                pos_x REAL NOT NULL,
                pos_y REAL NOT NULL,
                data_utc TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS auditoria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_utc TEXT NOT NULL,
                usuario TEXT NOT NULL,
                acao TEXT NOT NULL,
                resultado TEXT NOT NULL,
                detalhe TEXT
            )
        """)


def registrar_evento(usuario, acao, resultado, detalhe=""):
    data = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with conectar() as conn:
        conn.execute(
            """INSERT INTO auditoria
               (data_utc, usuario, acao, resultado, detalhe)
               VALUES (?, ?, ?, ?, ?)""",
            (data, usuario, acao, resultado, detalhe)
        )


def gerar_selo(assinante, assinatura_id, hash_original, data_utc, largura, altura, x, y):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(largura, altura))
    selo_largura, selo_altura = 255, 76

    # Mantém o selo dentro da página.
    x = max(0, min(float(x), largura - selo_largura))
    y = max(0, min(float(y), altura - selo_altura))

    pdf.setStrokeColorRGB(0.05, 0.35, 0.48)
    pdf.setFillColorRGB(0.93, 0.97, 0.98)
    pdf.roundRect(x, y, selo_largura, selo_altura, 7, stroke=1, fill=1)
    pdf.setFillColorRGB(0.05, 0.25, 0.35)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(x + 10, y + 57, "ASSINATURA - PROTOTIPO ACADEMICO")
    pdf.setFont("Helvetica", 9)
    pdf.drawString(x + 10, y + 42, f"Assinante: {assinante[:34]}")
    pdf.drawString(x + 10, y + 28, f"Data UTC: {data_utc}")
    pdf.drawString(x + 10, y + 14, f"ID: {assinatura_id}")
    pdf.setFont("Helvetica", 5.5)
    pdf.drawString(x + 10, y + 5, f"SHA-256 original: {hash_original[:42]}...")
    pdf.save()
    buffer.seek(0)
    return PdfReader(buffer).pages[0]


def assinar_pdf(caminho_entrada, caminho_saida, assinante, pagina_num, x, y):
    with open(caminho_entrada, "rb") as f:
        conteudo_original = f.read()

    if not conteudo_original.startswith(b"%PDF-"):
        raise ValueError("O arquivo selecionado não parece ser um PDF válido.")

    leitor = PdfReader(BytesIO(conteudo_original), strict=False)
    if leitor.is_encrypted:
        raise ValueError("Este protótipo não trabalha com PDFs protegidos por senha.")
    if len(leitor.pages) == 0:
        raise ValueError("O PDF não possui páginas.")
    if pagina_num < 1 or pagina_num > len(leitor.pages):
        raise ValueError(f"Escolha uma página entre 1 e {len(leitor.pages)}.")

    hash_original = sha256_bytes(conteudo_original)
    assinatura_id = str(uuid.uuid4())[:8].upper()
    data_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    writer = PdfWriter()

    for indice, pagina in enumerate(leitor.pages, start=1):
        if indice == pagina_num:
            largura = float(pagina.mediabox.width)
            altura = float(pagina.mediabox.height)
            selo = gerar_selo(
                assinante, assinatura_id, hash_original,
                data_utc, largura, altura, x, y
            )
            pagina.merge_page(selo)
        writer.add_page(pagina)

    with open(caminho_saida, "wb") as saida:
        writer.write(saida)

    hash_assinado = sha256_file(caminho_saida)
    with conectar() as conn:
        conn.execute("""
            INSERT INTO assinaturas
            (id, assinante, arquivo_original, hash_original, hash_assinado,
             pagina, pos_x, pos_y, data_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            assinatura_id, assinante, Path(caminho_entrada).name,
            hash_original, hash_assinado, pagina_num, float(x), float(y), data_utc
        ))

    registrar_evento(assinante, "Assinatura de PDF", "SUCESSO",
                     f"ID {assinatura_id}; página {pagina_num}")
    return assinatura_id, hash_assinado


def verificar_pdf(caminho):
    hash_atual = sha256_file(caminho)
    with conectar() as conn:
        registro = conn.execute(
            "SELECT * FROM assinaturas WHERE hash_assinado = ?",
            (hash_atual,)
        ).fetchone()

        if registro:
            return ("DOCUMENTO ÍNTEGRO",
                    f"Assinante: {registro['assinante']}\n"
                    f"ID da assinatura: {registro['id']}\n"
                    f"Data UTC: {registro['data_utc']}\n"
                    f"Hash SHA-256 confere.")

        # Procura o identificador do selo no texto do PDF. Isso é apenas
        # uma heurística de demonstração, não uma validação criptográfica.
        ids = conn.execute("SELECT id FROM assinaturas").fetchall()
        try:
            leitor = PdfReader(caminho, strict=False)
            texto = "\n".join((p.extract_text() or "") for p in leitor.pages)
        except Exception:
            texto = ""

        for item in ids:
            if item["id"] in texto:
                return ("DOCUMENTO ADULTERADO",
                        "Foi localizado um identificador de assinatura conhecido, "
                        "mas o hash do arquivo não corresponde ao documento registrado.")

    return ("ASSINATURA NÃO ENCONTRADA",
            "Não foi localizado um registro correspondente a este PDF.")


class Aplicacao:
    def __init__(self, root):
        self.root = root
        self.root.title("AssinaPDF | Protótipo acadêmico")
        self.root.geometry("920x650")
        self.root.minsize(820, 580)
        self.usuario = "Usuário demonstrativo"
        self.arquivo_assinar = tk.StringVar()
        self.arquivo_verificar = tk.StringVar()
        self.assinante = tk.StringVar(value="Antonio Adilson Costa")
        self.pagina = tk.StringVar(value="1")
        self.pos_x = tk.StringVar(value="40")
        self.pos_y = tk.StringVar(value="40")

        self.configurar_estilo()
        self.montar_interface()
        self.atualizar_auditoria()

    def configurar_estilo(self):
        self.root.configure(bg="#eef3f7")
        estilo = ttk.Style()
        estilo.theme_use("clam")
        estilo.configure("TFrame", background="#eef3f7")
        estilo.configure("Card.TFrame", background="white")
        estilo.configure("TLabel", background="#eef3f7", foreground="#243746",
                         font=("Segoe UI", 10))
        estilo.configure("Title.TLabel", font=("Segoe UI", 22, "bold"),
                         foreground="#123b52")
        estilo.configure("Sub.TLabel", font=("Segoe UI", 10), foreground="#607786")
        estilo.configure("TButton", font=("Segoe UI", 10, "bold"), padding=9)
        estilo.configure("Accent.TButton", background="#087e8b", foreground="white")
        estilo.map("Accent.TButton", background=[("active", "#066873")])
        estilo.configure("TNotebook", background="#eef3f7", borderwidth=0)
        estilo.configure("TNotebook.Tab", padding=(18, 10), font=("Segoe UI", 10, "bold"))
        estilo.configure("Treeview", rowheight=28, font=("Segoe UI", 9))
        estilo.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    def montar_interface(self):
        topo = ttk.Frame(self.root, padding=(25, 20, 25, 10))
        topo.pack(fill="x")
        ttk.Label(topo, text="AssinaPDF", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            topo,
            text="Sistema demonstrativo de assinatura e verificação de documentos PDF",
            style="Sub.TLabel"
        ).pack(anchor="w", pady=(3, 0))

        faixa = tk.Frame(self.root, bg="#123b52", height=34)
        faixa.pack(fill="x", padx=25, pady=(8, 14))
        faixa.pack_propagate(False)
        tk.Label(faixa, text="SESSÃO DE DEMONSTRAÇÃO  •  " + self.usuario,
                 bg="#123b52", fg="white", font=("Segoe UI", 9, "bold")).pack(
                     side="left", padx=12, pady=7)

        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill="both", expand=True, padx=25, pady=(0, 12))

        self.aba_assinar = ttk.Frame(self.tabs, padding=22)
        self.aba_verificar = ttk.Frame(self.tabs, padding=22)
        self.aba_auditoria = ttk.Frame(self.tabs, padding=22)
        self.tabs.add(self.aba_assinar, text="  Assinar PDF  ")
        self.tabs.add(self.aba_verificar, text="  Verificar PDF  ")
        self.tabs.add(self.aba_auditoria, text="  Auditoria  ")

        self.montar_aba_assinar()
        self.montar_aba_verificar()
        self.montar_aba_auditoria()

        rodape = ttk.Label(
            self.root,
            text="Protótipo acadêmico • Os PDFs são processados localmente e não são armazenados no banco.",
            style="Sub.TLabel"
        )
        rodape.pack(pady=(0, 12))

    def campo_arquivo(self, parent, variavel, comando):
        linha = ttk.Frame(parent)
        linha.pack(fill="x", pady=5)
        ttk.Entry(linha, textvariable=variavel).pack(side="left", fill="x", expand=True, ipady=5)
        ttk.Button(linha, text="Procurar...", command=comando).pack(side="left", padx=(8, 0))

    def montar_aba_assinar(self):
        ttk.Label(self.aba_assinar, text="Nova assinatura", font=("Segoe UI", 17, "bold")).pack(anchor="w")
        ttk.Label(self.aba_assinar, text="Selecione o PDF e informe os dados do selo visual.",
                  style="Sub.TLabel").pack(anchor="w", pady=(2, 16))

        ttk.Label(self.aba_assinar, text="Documento PDF").pack(anchor="w")
        self.campo_arquivo(self.aba_assinar, self.arquivo_assinar, self.selecionar_pdf_assinar)

        ttk.Label(self.aba_assinar, text="Nome do assinante").pack(anchor="w", pady=(13, 3))
        ttk.Entry(self.aba_assinar, textvariable=self.assinante).pack(fill="x", ipady=5)

        linha = ttk.Frame(self.aba_assinar)
        linha.pack(fill="x", pady=(13, 5))
        for titulo, variavel, largura in [
            ("Página", self.pagina, 12),
            ("Posição X (pt)", self.pos_x, 14),
            ("Posição Y (pt)", self.pos_y, 14)
        ]:
            grupo = ttk.Frame(linha)
            grupo.pack(side="left", padx=(0, 20))
            ttk.Label(grupo, text=titulo).pack(anchor="w")
            ttk.Entry(grupo, textvariable=variavel, width=largura).pack(ipady=4)

        ttk.Label(
            self.aba_assinar,
            text="X e Y são coordenadas em pontos, medidas a partir do canto inferior esquerdo da página.",
            style="Sub.TLabel", wraplength=760
        ).pack(anchor="w", pady=(5, 14))

        ttk.Button(self.aba_assinar, text="ASSINAR E SALVAR PDF",
                   style="Accent.TButton", command=self.executar_assinatura).pack(anchor="w")

        self.resultado_assinatura = tk.Label(
            self.aba_assinar, text="Aguardando seleção do documento.",
            bg="white", fg="#536b78", justify="left", anchor="w",
            padx=14, pady=14, font=("Segoe UI", 10), wraplength=760
        )
        self.resultado_assinatura.pack(fill="x", pady=(18, 0))

    def montar_aba_verificar(self):
        ttk.Label(self.aba_verificar, text="Verificar autenticidade", font=("Segoe UI", 17, "bold")).pack(anchor="w")
        ttk.Label(self.aba_verificar,
                  text="A verificação compara o hash SHA-256 do arquivo com os registros locais.",
                  style="Sub.TLabel").pack(anchor="w", pady=(2, 16))
        ttk.Label(self.aba_verificar, text="Documento PDF assinado").pack(anchor="w")
        self.campo_arquivo(self.aba_verificar, self.arquivo_verificar, self.selecionar_pdf_verificar)
        ttk.Button(self.aba_verificar, text="VERIFICAR DOCUMENTO",
                   style="Accent.TButton", command=self.executar_verificacao).pack(anchor="w", pady=14)

        self.resultado_verificacao = tk.Label(
            self.aba_verificar, text="Selecione um documento para iniciar a verificação.",
            bg="white", fg="#536b78", justify="left", anchor="w",
            padx=16, pady=18, font=("Segoe UI", 11), wraplength=760
        )
        self.resultado_verificacao.pack(fill="x", pady=(5, 0))

        ttk.Label(
            self.aba_verificar,
            text="Resultados possíveis: documento íntegro, documento adulterado ou assinatura não encontrada.",
            style="Sub.TLabel", wraplength=760
        ).pack(anchor="w", pady=12)

    def montar_aba_auditoria(self):
        ttk.Label(self.aba_auditoria, text="Histórico de atividades", font=("Segoe UI", 17, "bold")).pack(anchor="w")
        ttk.Label(self.aba_auditoria, text="Registros locais de assinaturas e verificações.",
                  style="Sub.TLabel").pack(anchor="w", pady=(2, 12))
        colunas = ("data", "usuario", "acao", "resultado", "detalhe")
        self.tabela = ttk.Treeview(self.aba_auditoria, columns=colunas, show="headings")
        titulos = {
            "data": ("Data UTC", 160), "usuario": ("Usuário", 150),
            "acao": ("Ação", 160), "resultado": ("Resultado", 100),
            "detalhe": ("Detalhes", 250)
        }
        for col, (titulo, largura) in titulos.items():
            self.tabela.heading(col, text=titulo)
            self.tabela.column(col, width=largura, anchor="w")
        self.tabela.pack(fill="both", expand=True)
        ttk.Button(self.aba_auditoria, text="Atualizar histórico",
                   command=self.atualizar_auditoria).pack(anchor="e", pady=10)

    def selecionar_pdf_assinar(self):
        caminho = filedialog.askopenfilename(
            title="Selecionar PDF", filetypes=[("Arquivos PDF", "*.pdf")]
        )
        if caminho:
            self.arquivo_assinar.set(caminho)
            try:
                total = len(PdfReader(caminho, strict=False).pages)
                self.pagina.set("1")
                messagebox.showinfo("PDF selecionado", f"Documento com {total} página(s).")
            except Exception as erro:
                messagebox.showerror("Erro", f"Não foi possível ler o PDF: {erro}")

    def selecionar_pdf_verificar(self):
        caminho = filedialog.askopenfilename(
            title="Selecionar PDF para verificar", filetypes=[("Arquivos PDF", "*.pdf")]
        )
        if caminho:
            self.arquivo_verificar.set(caminho)

    def executar_assinatura(self):
        entrada = self.arquivo_assinar.get().strip()
        nome = self.assinante.get().strip()
        if not entrada or not Path(entrada).is_file():
            messagebox.showwarning("Atenção", "Selecione um arquivo PDF.")
            return
        if not nome:
            messagebox.showwarning("Atenção", "Informe o nome do assinante.")
            return
        try:
            pagina = int(self.pagina.get())
            x, y = float(self.pos_x.get()), float(self.pos_y.get())
        except ValueError:
            messagebox.showwarning("Dados inválidos", "Página, X e Y devem ser valores numéricos.")
            return

        saida = filedialog.asksaveasfilename(
            title="Salvar PDF assinado", defaultextension=".pdf",
            initialfile=Path(entrada).stem + "_assinado.pdf",
            filetypes=[("Arquivos PDF", "*.pdf")]
        )
        if not saida:
            return
        try:
            assinatura_id, hash_assinado = assinar_pdf(
                entrada, saida, nome, pagina, x, y
            )
            self.resultado_assinatura.config(
                text=f"ASSINATURA CONCLUÍDA\n\nArquivo salvo em: {saida}\n"
                     f"Identificador: {assinatura_id}\n"
                     f"SHA-256 do PDF assinado: {hash_assinado}",
                fg="#12633b"
            )
            self.atualizar_auditoria()
            messagebox.showinfo("Sucesso", "PDF processado e salvo com o selo visual.")
        except Exception as erro:
            registrar_evento(nome, "Assinatura de PDF", "FALHA", str(erro))
            self.atualizar_auditoria()
            messagebox.showerror("Não foi possível assinar", str(erro))

    def executar_verificacao(self):
        caminho = self.arquivo_verificar.get().strip()
        if not caminho or not Path(caminho).is_file():
            messagebox.showwarning("Atenção", "Selecione um arquivo PDF.")
            return
        try:
            status, detalhe = verificar_pdf(caminho)
            cores = {
                "DOCUMENTO ÍNTEGRO": "#12633b",
                "DOCUMENTO ADULTERADO": "#a33b32",
                "ASSINATURA NÃO ENCONTRADA": "#8a6414"
            }
            self.resultado_verificacao.config(
                text=f"{status}\n\n{detalhe}", fg=cores[status]
            )
            registrar_evento(self.usuario, "Verificação de PDF", status, Path(caminho).name)
            self.atualizar_auditoria()
        except Exception as erro:
            messagebox.showerror("Erro na verificação", str(erro))

    def atualizar_auditoria(self):
        if not hasattr(self, "tabela"):
            return
        for item in self.tabela.get_children():
            self.tabela.delete(item)
        with conectar() as conn:
            registros = conn.execute(
                "SELECT * FROM auditoria ORDER BY id DESC LIMIT 200"
            ).fetchall()
        for r in registros:
            self.tabela.insert("", "end", values=(
                r["data_utc"], r["usuario"], r["acao"],
                r["resultado"], r["detalhe"] or ""
            ))


if __name__ == "__main__":
    inicializar_banco()
    janela = tk.Tk()
    app = Aplicacao(janela)
    janela.mainloop()
