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
QUALIDADE_JPEG = 85  # Reduzido de 95 para 85
COMPRESSAO_TIFF = 'tiff_lzw'  # Alterado de tiff_deflate para tiff_lzw (melhor compressão)

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
    async def gerar_relatorio_erros(erros, arquivos_invalidos, arquivos_com_senha, pasta_destino):
        """Gera um relatório de erros em arquivo .txt"""
        try:
            # Cria o nome do arquivo com timestamp
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            nome_arquivo = f"relatorio_erros_{timestamp}.txt"
            caminho_relatorio = pasta_destino / nome_arquivo

            with open(caminho_relatorio, 'w', encoding='utf-8') as f:
                f.write("=" * 50 + "\n")
                f.write("RELATÓRIO DE ERROS E ARQUIVOS NÃO PROCESSADOS\n")
                f.write("=" * 50 + "\n\n")

                # Seção de erros de conversão
                if erros:
                    f.write("ERROS DE CONVERSÃO:\n")
                    f.write("-" * 30 + "\n")
                    for erro in erros:
                        partes = erro.split(": ", 1)
                        if len(partes) == 2:
                            nome_arquivo, mensagem_erro = partes
                            f.write(f"Arquivo: {nome_arquivo}\n")
                            f.write(f"Motivo: {mensagem_erro}\n")
                            f.write("-" * 30 + "\n")
                        else:
                            f.write(f"{erro}\n")
                            f.write("-" * 30 + "\n")
                    f.write("\n")

                # Seção de arquivos não suportados
                if arquivos_invalidos:
                    f.write("ARQUIVOS NÃO SUPORTADOS:\n")
                    f.write("-" * 30 + "\n")
                    for arquivo in arquivos_invalidos:
                        f.write(f"• {arquivo}\n")
                    f.write("\n")

                # Seção de arquivos com senha
                if arquivos_com_senha:
                    f.write("ARQUIVOS COM SENHA:\n")
                    f.write("-" * 30 + "\n")
                    for arquivo in arquivos_com_senha:
                        f.write(f"• {arquivo.name}\n")
                    f.write("\n")
                    f.write("Estes arquivos foram movidos para a pasta: arquivos_com_senha\n")

                # Rodapé
                f.write("\n" + "=" * 50 + "\n")
                f.write(f"Relatório gerado em: {time.strftime('%d/%m/%Y %H:%M:%S')}\n")
                f.write("=" * 50 + "\n")

            return caminho_relatorio
        except Exception as e:
            print(f"[ERRO] Falha ao gerar relatório: {e}")
            return None

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
            # Cria pasta para arquivos com senha
            pasta_senha = destino / "arquivos_com_senha"
            pasta_senha.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            erro = f"Falha ao criar pasta destino {destino}: {e}"
            if atualizar_status:
                atualizar_status(f"⚠️ {erro}")
            return 0, [erro]

        #Contagem e validação de arquivos
        arquivos_para_processar = []
        arquivos_invalidos = []
        arquivos_com_senha = []
        
        for root, _, files in os.walk(origem):
            for file in files:
                caminho_arquivo = Path(root) / file
                ext = caminho_arquivo.suffix.lower()
                
                if ext in ['.pdf', '.tif', '.tiff', '.jpg', '.jpeg', '.png', '.bmp', '.gif', '.doc', '.docx']:
                    # Verifica se é um arquivo protegido
                    protegido, _ = await ConversorModel.verificar_arquivo_protegido(caminho_arquivo)
                    if protegido:
                        arquivos_com_senha.append(caminho_arquivo)
                    else:
                        arquivos_para_processar.append(caminho_arquivo)
                else:
                    arquivos_invalidos.append(caminho_arquivo.name)

        # Processa arquivos protegidos
        await ConversorModel.processar_arquivos_protegidos(arquivos_com_senha, pasta_senha, atualizar_status)

        if not arquivos_para_processar and not arquivos_com_senha:
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

        # Gera o relatório de erros
        caminho_relatorio = ConversorModel.gerar_relatorio_erros(
            erros_detalhados, arquivos_invalidos, arquivos_com_senha, destino
        )

        if atualizar_status:
            status_msg = [
                f"✅ Conversão concluída em {tempo_formatado}",
                f"📊 Resumo do processamento:",
                f"   • Total de arquivos processados: {arquivos_processados}",
                f"   • Arquivos com erro: {len(erros_detalhados)}",
                f"   • Arquivos ignorados: {len(arquivos_invalidos)}",
                f"   • Arquivos com senha: {len(arquivos_com_senha)}"
            ]
            
            if erros_detalhados:
                status_msg.append("\n❌ Erros encontrados:")
                for erro in erros_detalhados[:10]:
                    # Separa o nome do arquivo do erro
                    partes = erro.split(": ", 1)
                    if len(partes) == 2:
                        nome_arquivo, mensagem_erro = partes
                        # Traduz as mensagens de erro comuns
                        mensagem_erro = mensagem_erro.replace("FileNotFoundError", "Arquivo não encontrado")
                        mensagem_erro = mensagem_erro.replace("PermissionError", "Sem permissão para acessar o arquivo")
                        mensagem_erro = mensagem_erro.replace("IsADirectoryError", "O caminho é uma pasta, não um arquivo")
                        mensagem_erro = mensagem_erro.replace("NotADirectoryError", "O caminho não é uma pasta")
                        mensagem_erro = mensagem_erro.replace("OSError", "Erro no sistema operacional")
                        mensagem_erro = mensagem_erro.replace("ValueError", "Valor inválido")
                        mensagem_erro = mensagem_erro.replace("TypeError", "Tipo de dado inválido")
                        mensagem_erro = mensagem_erro.replace("ImportError", "Biblioteca necessária não encontrada")
                        mensagem_erro = mensagem_erro.replace("MemoryError", "Memória insuficiente")
                        mensagem_erro = mensagem_erro.replace("TimeoutError", "Tempo limite excedido")
                        status_msg.append(f"   • Arquivo: {nome_arquivo}")
                        status_msg.append(f"     Motivo: {mensagem_erro}")
                    else:
                        status_msg.append(f"   • {erro}")
                
                if len(erros_detalhados) > 10:
                    status_msg.append(f"   • ... ({len(erros_detalhados)-10} erros omitidos)")
            
            if arquivos_invalidos:
                status_msg.append("\n⚠️ Arquivos não suportados:")
                for arquivo in arquivos_invalidos[:5]:
                    status_msg.append(f"   • {arquivo}")
                if len(arquivos_invalidos) > 5:
                    status_msg.append(f"   • ... ({len(arquivos_invalidos)-5} arquivos omitidos)")

            if arquivos_com_senha:
                status_msg.append("\n🔒 Arquivos com senha:")
                for arquivo in arquivos_com_senha[:5]:
                    status_msg.append(f"   • {arquivo.name}")
                if len(arquivos_com_senha) > 5:
                    status_msg.append(f"   • ... ({len(arquivos_com_senha)-5} arquivos omitidos)")
                status_msg.append(f"   📁 Estes arquivos foram movidos para a pasta: arquivos_com_senha")

            if caminho_relatorio:
                status_msg.append(f"\n📝 Relatório detalhado gerado em: {caminho_relatorio.name}")

            atualizar_status("\n".join(status_msg))

        return arquivos_processados, erros_detalhados

    @staticmethod
    async def converter_imagem_para_pdf(caminho_origem, caminho_destino):
        #Converte uma imagem para PDF usando Pillow e ReportLab
        try:
            with Image.open(caminho_origem) as img:
                # Verifica se a imagem tem múltiplos frames (GIF, TIFF)
                try:
                    num_frames = getattr(img, "n_frames", 1)
                    if num_frames > 1:
                        # Se for multi-frame, cria uma pasta para o arquivo
                        pasta_destino = caminho_destino.parent / caminho_destino.stem
                        pasta_destino.mkdir(parents=True, exist_ok=True)
                        
                        # Converte cada frame para um PDF separado
                        for i in range(num_frames):
                            img.seek(i)
                            # Converte para RGB se necessário
                            if img.mode in ('RGBA', 'LA', 'P', '1'):
                                background = Image.new('RGB', img.size, (255, 255, 255))
                                if img.mode == 'RGBA':
                                    background.paste(img, mask=img.split()[-1])
                                else:
                                    background.paste(img)
                                img = background
                            elif img.mode == 'CMYK':
                                img = img.convert('RGB')

                            img_io = io.BytesIO()
                            img.save(img_io, format='JPEG', quality=QUALIDADE_JPEG, optimize=True)
                            img_io.seek(0)

                            pagina_destino = pasta_destino / f"pagina_{i+1:03d}.pdf"
                            c = canvas.Canvas(str(pagina_destino), pagesize=A4)
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
                    else:
                        # Se for uma única imagem, converte normalmente
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
                        img.save(img_io, format='JPEG', quality=QUALIDADE_JPEG, optimize=True)
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
                    # Se houver erro ao verificar frames, converte como imagem única
                    if img.mode in ('RGBA', 'LA', 'P', '1'):
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        if img.mode == 'RGBA':
                            background.paste(img, mask=img.split()[-1])
                        else:
                            background.paste(img)
                        img = background
                    elif img.mode == 'CMYK':
                        img = img.convert('RGB')

                    img_io = io.BytesIO()
                    img.save(img_io, format='JPEG', quality=QUALIDADE_JPEG, optimize=True)
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
            num_pages = len(pdf)
            
            if num_pages > 1:
                # Se for multi-página, cria uma pasta para o arquivo
                pasta_destino = caminho_destino.parent / caminho_destino.stem
                pasta_destino.mkdir(parents=True, exist_ok=True)
                
                # Converte cada página para um PDF separado
                for i in range(num_pages):
                    page = pdf[i]
                    pagina_destino = pasta_destino / f"pagina_{i+1:03d}.pdf"
                    new_pdf = pdfium.PdfDocument.new()
                    new_pdf.insert_pdf(pdf, from_page=i, to_page=i)
                    new_pdf.save(pagina_destino)
            else:
                # Se for uma única página, salva normalmente
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
                # Converter PDF para TIFF
                pdf = pdfium.PdfDocument(caminho_origem)
                num_pages = len(pdf)
                
                if num_pages > 1:
                    # Se for multi-página, cria uma pasta para o arquivo
                    pasta_destino = caminho_destino.parent / caminho_destino.stem
                    pasta_destino.mkdir(parents=True, exist_ok=True)
                    
                    # Converte cada página para um arquivo TIFF separado
                    for i in range(num_pages):
                        page = pdf[i]
                        bitmap = page.render(scale=DPI_PDF/72)
                        pil_image = bitmap.to_pil()
                        pagina_destino = pasta_destino / f"pagina_{i+1:03d}.tiff"
                        pil_image.save(pagina_destino, format='TIFF', compression=COMPRESSAO_TIFF)
                else:
                    # Se for uma única página, converte normalmente
                    page = pdf[0]
                    bitmap = page.render(scale=DPI_PDF/72)
                    pil_image = bitmap.to_pil()
                    pil_image.save(caminho_destino, format='TIFF', compression=COMPRESSAO_TIFF)
            else:
                # Converter imagem para TIFF
                with Image.open(caminho_origem) as img:
                    # Verifica se a imagem tem múltiplos frames (GIF, TIFF)
                    try:
                        num_frames = getattr(img, "n_frames", 1)
                        if num_frames > 1:
                            # Se for multi-frame, cria uma pasta para o arquivo
                            pasta_destino = caminho_destino.parent / caminho_destino.stem
                            pasta_destino.mkdir(parents=True, exist_ok=True)
                            
                            # Converte cada frame para um arquivo TIFF separado
                            for i in range(num_frames):
                                img.seek(i)
                                pagina_destino = pasta_destino / f"pagina_{i+1:03d}.tiff"
                                img.save(pagina_destino, format='TIFF', compression=COMPRESSAO_TIFF)
                        else:
                            # Se for uma única imagem, converte normalmente
                            img.save(caminho_destino, format='TIFF', compression=COMPRESSAO_TIFF)
                    except Exception as e:
                        # Se houver erro ao verificar frames, converte como imagem única
                        img.save(caminho_destino, format='TIFF', compression=COMPRESSAO_TIFF)
        except Exception as e:
            raise Exception(f"Falha ao converter para TIFF: {e}")

    @staticmethod
    async def verificar_arquivo_protegido(caminho_arquivo):
        """Verifica se um arquivo PDF está protegido por senha"""
        try:
            if caminho_arquivo.suffix.lower() == '.pdf':
                pdf = pdfium.PdfDocument(caminho_arquivo)
                return False, None
            return False, None
        except Exception as e:
            if "password" in str(e).lower() or "senha" in str(e).lower():
                return True, str(e)
            return False, str(e)

    @staticmethod
    async def mover_arquivo_protegido(arquivo, pasta_destino):
        """Move um arquivo protegido para a pasta de destino"""
        try:
            destino_arquivo = pasta_destino / arquivo.name
            shutil.copy2(arquivo, destino_arquivo)
            return True, None
        except Exception as e:
            return False, str(e)

    @staticmethod
    async def processar_arquivos_protegidos(arquivos, pasta_destino, atualizar_status=None):
        """Processa uma lista de arquivos protegidos"""
        resultados = []
        for arquivo in arquivos:
            sucesso, erro = await ConversorModel.mover_arquivo_protegido(arquivo, pasta_destino)
            if sucesso:
                resultados.append((arquivo.name, True, None))
                if atualizar_status:
                    atualizar_status(f"🔒 Arquivo com senha movido: {arquivo.name}")
            else:
                resultados.append((arquivo.name, False, erro))
                if atualizar_status:
                    atualizar_status(f"⚠️ Erro ao mover arquivo com senha {arquivo.name}: {erro}")
        return resultados

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