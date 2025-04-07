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

#Configurações
MAX_TAREFAS_SIMULTANEAS = 4
PAGINAS_POR_LOTE = 150
DPI_PDF = 150

#Diretório temporário
TEMP_DIR = Path(tempfile.gettempdir()) / "flet_converter_temp"
TEMP_DIR.mkdir(exist_ok=True)

class ConversorModel:
    @staticmethod
    async def limpar_temp():
        #Aqui limpa os arquivos temporários
        for file in TEMP_DIR.glob("*"):
            try:
                file.unlink()
            except Exception as e:
                print(f"[AVISO] Falha ao limpar arquivo temporário {file}: {e}")

    @staticmethod
    async def converter_para_pdf(origem, destino, atualizar_status=None, parar=False, formato="PDF"):

        #Converte arquivos para PDF ou TIFF com tratamento completo de erros
        #Retorna: (total_processado, erros_detalhados)
        
        if formato == "TIFF":
            try:
                import pypdfium2
            except ImportError:
                erro = "Biblioteca pypdfium2 não instalada. Execute: pip install pypdfium2"
                if atualizar_status:
                    atualizar_status(f"⚠️ {erro}")
                return 0, [erro]

        await ConversorModel.limpar_temp()
        origem = Path(origem)
        destino = Path(destino)

        if not origem.exists():
            erro = f"Pasta de origem não existe: {origem}"
            if atualizar_status:
                atualizar_status(f"⚠️ {erro}")
            return 0, [erro]

        try:
            destino.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            erro = f"Falha ao criar pasta destino {destino}: {e}"
            if atualizar_status:
                atualizar_status(f"⚠️ {erro}")
            return 0, [erro]

        #Contagem e validação de arquivos
        arquivos_para_processar = []
        arquivos_invalidos = []
        
        for root, _, files in os.walk(origem):
            for file in files:
                caminho_arquivo = Path(root) / file
                ext = caminho_arquivo.suffix.lower()
                
                if ext in ['.pdf', '.tif', '.tiff', '.jpg', '.jpeg', '.png', '.bmp', '.gif', '.doc', '.docx']:
                    arquivos_para_processar.append(caminho_arquivo)
                else:
                    arquivos_invalidos.append(caminho_arquivo.name)

        if not arquivos_para_processar:
            erro = "Nenhum arquivo suportado encontrado para conversão"
            if atualizar_status:
                atualizar_status(f"⚠️ {erro}")
            return 0, [erro]

        #Este é o processamento principal
        arquivos_processados = 0
        erros_detalhados = []
        start_time = time.time()
        semaforo = asyncio.Semaphore(MAX_TAREFAS_SIMULTANEAS)

        async def processar_arquivo(caminho_arquivo):
            nonlocal arquivos_processados, erros_detalhados
            async with semaforo:
                if parar:
                    return

                try:
                    caminho_relativo = caminho_arquivo.relative_to(origem)
                    ext = caminho_arquivo.suffix.lower()
                    
                    #Define destino com extensão correta
                    destino_arquivo = destino / caminho_relativo
                    destino_arquivo = destino_arquivo.with_suffix('.tiff' if formato == "TIFF" else '.pdf')
                    
                    #Cria estrutura de pastas
                    try:
                        destino_arquivo.parent.mkdir(parents=True, exist_ok=True)
                    except Exception as e:
                        raise Exception(f"Falha ao criar diretório: {e}")

                    #Executa conversão conforme formato
                    if formato == "PDF":
                        if ext == '.pdf':
                            await ConversorModel.ajustar_pdf(caminho_arquivo, destino_arquivo)
                        elif ext in ['.tif', '.tiff', '.jpg', '.jpeg', '.png', '.bmp', '.gif']:
                            await ConversorModel.converter_imagem_para_pdf(caminho_arquivo, destino_arquivo)
                        elif ext in ['.doc', '.docx']:
                            await ConversorModel.converter_word_para_pdf(caminho_arquivo, destino_arquivo)
                    elif formato == "TIFF":
                        await ConversorModel.converter_para_tiff(caminho_arquivo, destino_arquivo)

                    #Atualiza status
                    arquivos_processados += 1
                    if atualizar_status:
                        status_msg = (
                            f"⏳ Convertendo: {caminho_arquivo.name}\n"
                            f"Progresso: {arquivos_processados}/{len(arquivos_para_processar)}\n"
                            f"Erros: {len(erros_detalhados)}"
                        )
                        atualizar_status(status_msg)

                except Exception as e:
                    erro_msg = f"{caminho_arquivo.name}: {type(e).__name__} - {str(e)}"
                    erros_detalhados.append(erro_msg)
                    if atualizar_status:
                        atualizar_status("", erro=erro_msg)  #Passa o erro para a interface
                    print(f"[ERRO] {erro_msg}")

        #Executa tarefas em paralelo
        tarefas = [processar_arquivo(arquivo) for arquivo in arquivos_para_processar]
        await asyncio.gather(*tarefas)
        await ConversorModel.limpar_temp()

        #Gera relatório final
        tempo_total = time.time() - start_time
        horas, resto = divmod(tempo_total, 3600)
        minutos, segundos = divmod(resto, 60)
        tempo_formatado = f"{int(horas)}h {int(minutos)}m {int(segundos)}s"

        if atualizar_status:
            status_msg = [
                f"✅ Conversão concluída em {tempo_formatado}",
                f"Arquivos processados: {arquivos_processados}",
                f"Arquivos com erro: {len(erros_detalhados)}",
                f"Arquivos ignorados: {len(arquivos_invalidos)}"
            ]
            
            if erros_detalhados:
                status_msg.append("\nErros encontrados:")
                status_msg.extend(f"• {erro}" for erro in erros_detalhados[:10])
                if len(erros_detalhados) > 10:
                    status_msg.append(f"• ... ({len(erros_detalhados)-10} erros omitidos)")
            
            if arquivos_invalidos:
                status_msg.append("\nArquivos não suportados:")
                status_msg.extend(f"• {arquivo}" for arquivo in arquivos_invalidos[:3])
                if len(arquivos_invalidos) > 3:
                    status_msg.append(f"• ... ({len(arquivos_invalidos)-3} arquivos omitidos)")

            atualizar_status("\n".join(status_msg))

        return arquivos_processados, erros_detalhados

    @staticmethod
    async def converter_imagem_para_pdf(caminho_origem, caminho_destino):
        #Converte uma imagem para PDF usando Pillow e ReportLab
        try:
            with Image.open(caminho_origem) as img:
                #Converte para RGB se for PNG com transparência ou modo P (paleta)
                if img.mode in ('RGBA', 'LA', 'P', '1'):  # Adicionamos 'P' e '1' (preto e branco)
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    
                    if img.mode == 'RGBA':
                        background.paste(img, mask=img.split()[-1])  # Preserva transparência
                    else:
                        background.paste(img)  # Para modos P e 1
                    
                    img = background
                elif img.mode == 'CMYK':
                    img = img.convert('RGB')

                img_io = io.BytesIO()
                img.save(img_io, format='JPEG', quality=95)
                img_io.seek(0)

                c = canvas.Canvas(str(caminho_destino), pagesize=A4)
                img_width, img_height = img.size
                aspect = img_height / float(img_width)

                pdf_width = A4[0] - 2 * 72  # Margens de 1 polegada
                pdf_height = pdf_width * aspect

                if pdf_height > A4[1] - 2 * 72:  # Ajuste se for muito alto
                    pdf_height = A4[1] - 2 * 72
                    pdf_width = pdf_height / aspect

                x = (A4[0] - pdf_width) / 2
                y = (A4[1] - pdf_height) / 2

                c.drawImage(ImageReader(img_io), x, y, pdf_width, pdf_height)
                c.save()
                
        except Exception as e:
            raise Exception(f"Falha ao converter imagem para PDF: {e}")

    @staticmethod
    async def ajustar_pdf(caminho_origem, caminho_destino):
        #Otimiza e ajusta PDFs existentes
        try:
            pdf = pdfium.PdfDocument(caminho_origem)
            pdf.save(caminho_destino)
        except Exception as e:
            raise Exception(f"Falha ao processar PDF: {e}")

    @staticmethod
    async def converter_word_para_pdf(caminho_origem, caminho_destino):
        """Converte documentos Word para PDF"""
        try:
            #Usa docx2pdf que funciona tanto para .doc quanto .docx
            docx2pdf_convert(str(caminho_origem), str(caminho_destino))
        except Exception as e:
            raise Exception(f"Falha ao converter documento Word: {e}")

    @staticmethod
    async def converter_para_tiff(caminho_origem, caminho_destino):
        """Converte arquivos para TIFF"""
        try:
            if caminho_origem.suffix.lower() == '.pdf':
                #Converter PDF para TIFF
                pdf = pdfium.PdfDocument(caminho_origem)
                page = pdf[0]  #Pega a primeira página
                bitmap = page.render(scale=DPI_PDF/72)
                pil_image = bitmap.to_pil()
                pil_image.save(caminho_destino, format='TIFF', compression='tiff_deflate')
            else:
                #Converter imagem para TIFF
                with Image.open(caminho_origem) as img:
                    img.save(caminho_destino, format='TIFF', compression='tiff_deflate')
        except Exception as e:
            raise Exception(f"Falha ao converter para TIFF: {e}")

def extrair_todos_zips(caminho_origem, atualizar_status=None):
    """Extrai arquivos compactados com tratamento de erros"""
    erros = []
    
    for arquivo in os.listdir(caminho_origem):
        caminho_arquivo = os.path.join(caminho_origem, arquivo)
        try:
            if arquivo.endswith(".zip"):
                with zipfile.ZipFile(caminho_arquivo, 'r') as zip_ref:
                    zip_ref.extractall(caminho_origem)
                    if atualizar_status:
                        atualizar_status(f"✅ Extraído: {arquivo}")
            elif any(arquivo.endswith(ext) for ext in [".tar", ".tar.gz", ".tgz"]):
                with tarfile.open(caminho_arquivo, 'r') as tar_ref:
                    tar_ref.extractall(caminho_origem)
                    if atualizar_status:
                        atualizar_status(f"✅ Extraído: {arquivo}")
        except Exception as e:
            erro = f"Erro ao extrair {arquivo}: {e}"
            erros.append(erro)
            if atualizar_status:
                atualizar_status(f"⚠️ {erro}")
            print(f"[ERRO] {erro}")

    time.sleep(5)  #Espera 5segundos para exclusão segura
    
    #Remove arquivos compactados
    for arquivo in os.listdir(caminho_origem):
        caminho_arquivo = os.path.join(caminho_origem, arquivo)
        if any(arquivo.endswith(ext) for ext in [".zip", ".tar", ".tar.gz", ".tgz"]):
            try:
                os.remove(caminho_arquivo)
                if atualizar_status:
                    atualizar_status(f"🗑️ Removido: {arquivo}")
            except Exception as e:
                erro = f"Falha ao remover {arquivo}: {e}"
                erros.append(erro)
                if atualizar_status:
                    atualizar_status(f"⚠️ {erro}")
                print(f"[ERRO] {erro}")

    return erros