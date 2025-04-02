import os
import time
import asyncio
from model.converter import ConversorModel, extrair_todos_zips
from model.converter import ConversorModel
from datetime import datetime

class ConversorViewModel:
    def __init__(self):
        self.parar = False

    async def converter(self, origem, destino, atualizar_status=None, formato="PDF"):
        try:
            total, erros = await ConversorModel.converter_para_pdf(
                origem, destino, 
                atualizar_status,
                self.parar, 
                formato
            )
            return (total, erros)
            
        except Exception as e:
            if atualizar_status:
                atualizar_status(f"⚠️ Erro crítico: {str(e)}")
            return (0, [str(e)])

        inicio = time.time()
        await ConversorModel.converter_para_pdf(origem, destino, atualizar_status, self.parar, formato)
        fim = time.time()
        tempo_total = fim - inicio

        horas, resto = divmod(tempo_total, 3600)
        minutos, segundos = divmod(resto, 60)
        tempo_formatado = f"{int(horas)}h {int(minutos)}m {int(segundos)}s"

        return f"✅ {total_arquivos} arquivos convertidos em {tempo_formatado}."

def iniciar_conversao(origem, destino, atualizar_status=None, formato="PDF"):
    vm = ConversorViewModel()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        inicio = time.time()
        total_processados, erros = loop.run_until_complete(
            vm.converter(origem, destino, atualizar_status, formato)
        )
        
        # Calcula o tempo decorrido
        tempo_decorrido = time.time() - inicio
        horas, resto = divmod(tempo_decorrido, 3600)
        minutos, segundos = divmod(resto, 60)
        tempo_formatado = f"{int(horas)}h {int(minutos)}m {int(segundos)}s"
        
        # Mensagem de resumo
        mensagem_resumo = [
            f"✅ Conversão concluída em {tempo_formatado}",
            f"Arquivos convertidos: {total_processados - len(erros)}",
            f"Arquivos com erro: {len(erros)}",
            f"Total processado: {total_processados}"
        ]
        
        if erros:
            caminho_relatorio = gerar_relatorio_erros(erros, destino)
            mensagem_resumo.append(f"\nRelatório de erros gerado em:\n{os.path.basename(caminho_relatorio)}")
        
        if atualizar_status:
            atualizar_status("\n".join(mensagem_resumo))
            
    finally:
        loop.close()

def iniciar_extracao(origem, atualizar_status=None):


    try:
        extrair_todos_zips(origem, atualizar_status=atualizar_status)
        if atualizar_status:
            atualizar_status("Extração concluída com sucesso!")
    except Exception as e:
        if atualizar_status:
            atualizar_status(f"Erro durante a extração: {e}")
        print(f"[ERRO] {e}")

def parar_conversao(vm):
    vm.parar = True

def gerar_relatorio_erros(erros, pasta_destino):
    """Gera arquivo TXT com erros na pasta de destino"""
    if not erros:
        return None
        
    try:
        from datetime import datetime
        os.makedirs(pasta_destino, exist_ok=True)
        nome_arquivo = f"erros_conversao_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        caminho_completo = os.path.join(pasta_destino, nome_arquivo)
        
        with open(caminho_completo, 'w', encoding='utf-8') as f:
            f.write("RELATÓRIO DE ERROS - DOCUMENTA\n")
            f.write("="*40 + "\n")
            f.write(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n")
            f.write("\n".join(erros))
            
        return caminho_completo
    except Exception as e:
        print(f"Erro ao gerar relatório: {e}")
        return None