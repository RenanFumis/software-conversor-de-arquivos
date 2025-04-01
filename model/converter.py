import os
import zipfile
import tarfile
import shutil
import time
import asyncio
from pathlib import Path
from PIL import Image
import pypdfium2 as pdfium
from docx2pdf import convert as docx2pdf_convert
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import io
import tempfile

MAX_TAREFAS_SIMULTANEAS = 4
PAGINAS_POR_LOTE = 150
DPI_PDF = 150

#Diretório temporário
TEMP_DIR = Path(tempfile.gettempdir()) / "flet_converter_temp"
TEMP_DIR.mkdir(exist_ok=True)

class ConversorModel:
    @staticmethod
    async def limpar_temp():
        """Limpa arquivos temporários"""
        for file in TEMP_DIR.glob("*"):
            try:
                file.unlink()
            except:
                pass

    @staticmethod
    async def converter_para_pdf(origem, destino, atualizar_status=None, parar=False, formato="PDF"):
        """Converte todos os arquivos para PDF ou TIFF, incluindo subpastas."""
        if formato == "TIFF":
            try:
                import pypdfium2
            except ImportError:
                if atualizar_status:
                    atualizar_status("⚠️ Erro: pypdfium2 não está instalado. Instale com: pip install pypdfium2")
                return

        await ConversorModel.limpar_temp()
        origem = Path(origem)
        destino = Path(destino)

        if not destino.exists():
            destino.mkdir(parents=True, exist_ok=True)

        #Conta todos os arquivos em todas as subpastas
        total_arquivos = 0
        arquivos_para_processar = []
        for root, _, files in os.walk(origem):
            for file in files:
                caminho_arquivo = Path(root) / file
                #Verifica se é um tipo de arquivo suportado
                if caminho_arquivo.suffix.lower() in ['.pdf', '.tif', '.tiff', '.jpg', '.jpeg', '.png', '.bmp', '.gif', '.doc', '.docx']:
                    total_arquivos += 1
                    arquivos_para_processar.append(caminho_arquivo)

        if total_arquivos == 0:
            if atualizar_status:
                atualizar_status("⚠️ Nenhum arquivo suportado encontrado para conversão.")
            return

        arquivos_processados = 0
        arquivos_com_erro = []
        start_time = time.time()
        semaforo = asyncio.Semaphore(MAX_TAREFAS_SIMULTANEAS)

        async def processar_arquivo(caminho_arquivo):
            nonlocal arquivos_processados
            async with semaforo:
                if parar:
                    return
                try:
                    #Calcula o caminho relativo
                    caminho_relativo = caminho_arquivo.relative_to(origem)
                    destino_arquivo = destino / caminho_relativo
                    
                    if formato == "TIFF":
                        destino_arquivo = destino_arquivo.with_suffix('.tiff')
                    else:
                        destino_arquivo = destino_arquivo.with_suffix('.pdf')

                    destino_arquivo.parent.mkdir(parents=True, exist_ok=True)

                    #Processa conforme o tipo
                    if formato == "PDF":
                        if caminho_arquivo.suffix.lower() == '.pdf':
                            await ConversorModel.ajustar_pdf(caminho_arquivo, destino_arquivo)
                        elif caminho_arquivo.suffix.lower() in ['.tif', '.tiff', '.jpg', '.jpeg', '.png', '.bmp', '.gif']:
                            await ConversorModel.converter_imagem_para_pdf(caminho_arquivo, destino_arquivo)
                        elif caminho_arquivo.suffix.lower() in ['.doc', '.docx']:
                            await ConversorModel.converter_word_para_pdf(caminho_arquivo, destino_arquivo)
                    elif formato == "TIFF":
                        if caminho_arquivo.suffix.lower() in ['.tif', '.tiff', '.jpg', '.jpeg', '.png', '.bmp', '.gif', '.pdf']:
                            await ConversorModel.converter_imagem_para_tiff(caminho_arquivo, destino_arquivo)

                    arquivos_processados += 1
                    if atualizar_status:
                        atualizar_status(f"⏳ Convertendo: {caminho_arquivo.name}\nStatus... ({arquivos_processados}/{total_arquivos})")

                except Exception as e:
                    print(f"[ERRO] Falha ao processar {caminho_arquivo}: {e}")
                    arquivos_com_erro.append(caminho_arquivo.name)

        #Cria e executa todas as tarefas
        tarefas = [processar_arquivo(arquivo) for arquivo in arquivos_para_processar]
        await asyncio.gather(*tarefas)
        await ConversorModel.limpar_temp()

        #Cálculo do tempo decorrido
        tempo_total = time.time() - start_time
        horas, resto = divmod(tempo_total, 3600)
        minutos, segundos = divmod(resto, 60)
        tempo_formatado = f"{int(horas)}h {int(minutos)}m {int(segundos)}s"

        if atualizar_status:
            mensagem = (f"Conversão concluída em {tempo_formatado}\n"
                       f"Processados: {arquivos_processados}\n"
                       f"Erros: {len(arquivos_com_erro)}")
            atualizar_status(mensagem)

    @staticmethod
    async def converter_imagem_para_pdf(caminho_arquivo, destino_arquivo):
        """Converte imagem para PDF A4 com proporção mantida"""
        try:
            with Image.open(caminho_arquivo) as img:
                #Converte para RGB se for PNG com transparência
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                
                #Cria PDF em memória
                packet = io.BytesIO()
                can = canvas.Canvas(packet, pagesize=A4)
                
                #Calcula dimensões mantendo proporção
                img_width, img_height = img.size
                a4_width, a4_height = A4
                ratio = min(a4_width/img_width, a4_height/img_height) * 0.9  # 90% da página
                new_width = img_width * ratio
                new_height = img_height * ratio
                x = (a4_width - new_width) / 2
                y = (a4_height - new_height) / 2
                
                #Salvar imagem em memória
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='PNG', quality=95)
                img_byte_arr.seek(0)
                
                #Adicionar ao PDF
                can.drawImage(ImageReader(img_byte_arr), x, y, width=new_width, height=new_height)
                can.save()
                
                #Salvar PDF final
                with open(destino_arquivo, 'wb') as f:
                    f.write(packet.getvalue())
        except Exception as e:
            print(f"[ERRO] Falha ao converter {caminho_arquivo}: {e}")
            raise

    @staticmethod
    async def ajustar_pdf(caminho_arquivo, destino_arquivo):
        """Copia PDFs existentes (pode ser expandido para redimensionar)"""
        try:
            shutil.copy2(caminho_arquivo, destino_arquivo)
        except Exception as e:
            print(f"[ERRO] Falha ao copiar PDF {caminho_arquivo}: {e}")
            raise

    @staticmethod
    async def converter_word_para_pdf(caminho_arquivo, destino_arquivo):
        """Converte Word para PDF usando docx2pdf"""
        try:
            docx2pdf_convert(str(caminho_arquivo), str(destino_arquivo))
        except Exception as e:
            print(f"[ERRO] Falha ao converter Word {caminho_arquivo}: {e}")
            raise

    @staticmethod
    async def converter_imagem_para_tiff(caminho_arquivo, destino_arquivo):
        """Converte imagem ou PDF para TIFF (multipágina para PDFs)"""
        try:
            if caminho_arquivo.suffix.lower() == '.pdf':
                #Converter PDF para TIFF multipágina
                pdf = pdfium.PdfDocument(str(caminho_arquivo))
                images = []
                
                #Renderiza as páginas
                for page_number in range(len(pdf)):
                    page = pdf.get_page(page_number)
                    bitmap = page.render(scale=DPI_PDF/72)
                    pil_image = bitmap.to_pil()
                    images.append(pil_image)
                
                #Salva como TIFF multipágina
                if len(images) > 0:
                    images[0].save(
                        destino_arquivo,
                        format="TIFF",
                        compression="tiff_deflate",
                        save_all=True,
                        append_images=images[1:] if len(images) > 1 else []
                    )
            else:
                #Converter imagem para TIFF
                with Image.open(caminho_arquivo) as img:
                    img.save(destino_arquivo, format="TIFF", compression="tiff_deflate")
                    
        except Exception as e:
            print(f"[ERRO] Falha ao converter {caminho_arquivo}: {e}")
            raise

def extrair_todos_zips(caminho_origem, atualizar_status=None):

    for arquivo in os.listdir(caminho_origem):
        caminho_arquivo = os.path.join(caminho_origem, arquivo)
        if arquivo.endswith(".zip"):
            with zipfile.ZipFile(caminho_arquivo, 'r') as zip_ref:
                zip_ref.extractall(caminho_origem)
                if atualizar_status:
                    atualizar_status(f"Extraído: {arquivo}")
        elif arquivo.endswith(".tar") or arquivo.endswith(".tar.gz") or arquivo.endswith(".tgz"):
            with tarfile.open(caminho_arquivo, 'r') as tar_ref:
                tar_ref.extractall(caminho_origem)
                if atualizar_status:
                    atualizar_status(f"Extraído: {arquivo}")

    #Espera 5 segundos antes de excluir os arquivos ZIP/TAR
    time.sleep(5)
    for arquivo in os.listdir(caminho_origem):
        caminho_arquivo = os.path.join(caminho_origem, arquivo)
        if arquivo.endswith((".zip", ".tar", ".tar.gz", ".tgz")):
            os.remove(caminho_arquivo)
            if atualizar_status:
                atualizar_status(f"Removido: {arquivo}")