# AssinaPDF — Protótipo acadêmico

Aplicação desktop didática em Python com interface gráfica Tkinter para demonstrar:
- seleção de um PDF;
- inserção de selo visual em página escolhida;
- registro de metadados e hashes SHA-256 em SQLite;
- verificação de integridade por comparação de hash;
- histórico local de auditoria.

## Requisitos
- Python 3.10 ou superior
- Tkinter (normalmente incluído na instalação padrão do Python)
- Bibliotecas listadas em `requirements.txt`

## Como executar no Windows
1. Extraia o ZIP.
2. Abra o terminal na pasta `assinatura_pdf_demo`.
3. Instale as dependências:
   `py -m pip install -r requirements.txt`
4. Execute:
   `py main.py`

O banco `assinaturas.db` será criado automaticamente na primeira execução.

## Como demonstrar
1. Abra a aba **Assinar PDF**.
2. Selecione um PDF de teste.
3. Informe o nome do assinante, a página e as coordenadas X/Y.
4. Clique em **Assinar e salvar PDF** e escolha onde salvar.
5. Abra **Verificar PDF**, selecione o PDF gerado e verifique o resultado.
6. Para demonstrar adulteração, faça uma cópia do PDF assinado e altere seu conteúdo ou salve novamente por outro editor; depois verifique a cópia.
7. A aba **Auditoria** mostra as ações realizadas.

## Limites importantes do protótipo
Esta aplicação é uma demonstração acadêmica simplificada, não um serviço de assinatura digital com validade jurídica.

- O selo inserido é **visual**. Não é uma assinatura criptográfica PDF Signature embutida conforme ISO 32000.
- A verificação compara o hash SHA-256 do arquivo com o hash registrado localmente. Ela detecta alteração do arquivo registrado, mas não valida certificado digital, cadeia ICP-Brasil ou assinatura criptográfica.
- O identificador impresso no selo é usado apenas como indício auxiliar para classificar um arquivo alterado; isso não é prova criptográfica.
- O login, passkeys/WebAuthn, TOTP, JWT, CORS, CSRF, rate limiting e cabeçalhos HTTP não foram implementados nesta versão desktop.
- O SQLite guarda apenas metadados, hashes e auditoria. Os PDFs não são armazenados no banco.
- O histórico é uma tabela de auditoria demonstrativa; não possui garantia técnica de imutabilidade contra administrador do computador.

## Correspondência com o documento do projeto
A interface demonstra o fluxo geral das seções 8 e 9 do documento: selecionar e processar PDF, posicionar selo, calcular hashes, registrar metadados, devolver o arquivo e verificar integridade. Os demais requisitos de segurança devem ser tratados como evolução do projeto completo.
