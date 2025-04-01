import os
import time
import asyncio
from model.converter import ConversorModel, extrair_todos_zips
from model.converter import ConversorModel

class ConversorViewModel:
    def __init__(self):
        self.parar = False

    async def converter(self, origem, destino, atualizar_status=None, formato="PDF"):
        if not origem or not destino:
            return "⚠️ Erro: Caminhos de origem ou destino não definidos."

        arquivos = [f for f in os.listdir(origem) if os.path.isfile(os.path.join(origem, f))]
        total_arquivos = len(arquivos)

        if total_arquivos == 0:
            return "⚠️ Nenhum arquivo encontrado para conversão."

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
    loop.run_until_complete(vm.converter(origem, destino, atualizar_status, formato))
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