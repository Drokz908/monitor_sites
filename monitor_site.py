import requests
import sqlite3
from datetime import datetime
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import os

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# Obtém as credenciais do arquivo .env
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT")) if os.getenv("SMTP_PORT") else 587 # Converte a porta para inteiro, com fallback
# -------------------------------

# --- Configuração de Logging para arquivo ---

logging.basicConfig(filename='monitor_sites.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')


def initialize_database():
    """
    Inicializa o banco de dados 'monitor.db' e cria a tabela 'monitoramento_sites'
    se ela ainda não existir. Esta função garante que a estrutura do BD esteja pronta.
    """
    conn = sqlite3.connect("monitor.db")
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS monitoramento_sites (
        id_site INTEGER PRIMARY KEY AUTOINCREMENT,
        site TEXT NOT NULL,
        status_code INTEGER,
        status_text TEXT NOT NULL,
        data_hora TEXT NOT NULL
    )
    """)
    conn.commit()
    conn.close()
    logging.info("Banco de dados 'monitor.db' e tabela 'monitoramento_sites' verificados/criados com sucesso.")

def enviar_alerta_email(assunto, mensagem_html):
    """
    Envia um alerta por e-mail usando as credenciais configuradas no .env.
    A mensagem pode conter formatação HTML.
    """
    # Verifica se todas as credenciais de e-mail estão configuradas
    if not all([EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER, SMTP_SERVER, SMTP_PORT]):
        logging.error("Credenciais de e-mail não configuradas corretamente no .env. Alerta não enviado.")
        return

    msg = MIMEMultipart("alternative")
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg['Subject'] = assunto

    # Anexa a mensagem HTML ao e-mail
    msg.attach(MIMEText(mensagem_html, 'html'))

    try:
        # Conecta ao servidor SMTP
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls() # Inicia a criptografia TLS para comunicação segura
            server.login(EMAIL_SENDER, EMAIL_PASSWORD) # Faz login no servidor SMTP
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string()) # Envia o e-mail
            logging.info(f"Alerta de e-mail enviado: '{assunto}' para {EMAIL_RECEIVER}")
    except smtplib.SMTPAuthenticationError:
        logging.error("Erro de autenticação SMTP. Verifique seu email/senha de aplicativo no .env.")
    except smtplib.SMTPConnectError as e:
        logging.error(f"Erro de conexão SMTP: {e}. Verifique o servidor e a porta SMTP no .env.")
    except Exception as e:
        logging.error(f"Erro inesperado ao enviar e-mail: {e}")

def verificar_site(url):
    """
    Verifica o status de um site fazendo uma requisição HTTP GET.
    Retorna o código de status e uma mensagem descritiva.
    """
    try:
        response = requests.get(url, timeout=5) # Timeout de 5 segundos para a requisição
        response.raise_for_status() # Lança uma exceção para códigos de status 4xx/5xx
        return response.status_code, "OK"
    except requests.exceptions.SSLError:
        return None, "Erro SSL: Problema com certificado de segurança."
    except requests.exceptions.ConnectionError:
        return None, "Erro de Conexão: Não foi possível conectar ao site."
    except requests.exceptions.Timeout:
        return None, "Timeout: O site não respondeu no tempo esperado."
    except requests.exceptions.RequestException as e:
        # Captura outros erros de requisição, como 404, 500, etc.
        if e.response is not None:
            return e.response.status_code, f"Erro HTTP: {e.response.status_code} - {e.response.reason}"
        return None, f"Erro na Requisição: {e}"
    except Exception as e:
        return None, f"Erro Inesperado: {e}"

def registrar_status(site, status_code, status_text):
    """
    Registra o status da verificação de um site na tabela 'monitoramento_sites' do banco de dados.
    """
    conn = sqlite3.connect("monitor.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO monitoramento_sites (site, status_code, status_text, data_hora)
        VALUES (?, ?, ?, ?)
    """, (site, status_code, status_text, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    logging.info(f"Status registrado no BD: [{site}] -> {status_code} | {status_text}")

if __name__ == "__main__":
    # Garante que o banco de dados e a tabela estejam criados antes de iniciar o monitoramento
    initialize_database()

    try:
        with open("sites.txt", "r") as arquivo:
            # Lê os sites do arquivo, removendo espaços e linhas vazias
            sites = [linha.strip() for linha in arquivo if linha.strip()]
        if not sites:
            logging.warning("O arquivo 'sites.txt' está vazio. Nenhum site para monitorar.")
            print("Aviso: O arquivo 'sites.txt' está vazio. Nenhum site para monitorar.")
            exit()
    except FileNotFoundError:
        logging.error("Erro: O arquivo 'sites.txt' não foi encontrado. Crie-o com as URLs dos sites.")
        print("Erro: O arquivo 'sites.txt' não foi encontrado.")
        exit()

    logging.info("Iniciando verificação de sites.")
    print("\n--- Iniciando Verificação de Sites ---")

    for site in sites:
        codigo, texto = verificar_site(site) # Verifica o status do site
        registrar_status(site, codigo, texto) # Registra o status no banco de dados

        log_message = f"[{site}] -> {codigo if codigo is not None else 'N/A'} | {texto}"
        print(log_message) # Imprime no console
        logging.info(log_message) # Registra no arquivo de log

        # Lógica para enviar alerta por e-mail:
        # Alerta se o código não for 200 (OK) ou se for None (erro de conexão/SSL/timeout)
        if codigo != 200 or codigo is None:
            assunto_email = f"ALERTA: Problema com o site {site}"
            mensagem_html = f"""
            <html>
            <body>
                <p><b>ALERTA!</b> O site <a href="{site}">{site}</a> está com problemas!</p>
                <p><b>Status:</b> {codigo if codigo is not None else 'N/A'}</p>
                <p><b>Detalhes:</b> <i>{texto}</i></p>
                <p><b>Horário:</b> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>
            </body>
            </html>
            """
            enviar_alerta_email(assunto_email, mensagem_html)

    logging.info("Verificação de sites concluída.")
    print("--- Verificação de Sites Concluída ---")
