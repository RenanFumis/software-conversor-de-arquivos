import os
import time
import asyncio
from model.converter import ConversorModel, extrair_todos_zips
from datetime import datetime
from pathlib import Path

class ConversorViewModel:
    def __init__(self):
        self.parar = False
        self.arquivos_protegidos = []
        self.resultados_protegidos = []
        self.status_atual = ""
        self.erro_atual = None

    def atualizar_status(self, mensagem, erro=None):
        """Atualiza o status atual do processamento"""
        self.status_atual = mensagem
        self.erro_atual = erro

    async def extrair_arquivos(self, caminho_origem, callback_status=None):
        """Extrai arquivos compactados"""
        try:
            erros = extrair_todos_zips(caminho_origem, callback_status)
            return len(erros) == 0, erros
        except Exception as e:
            return False, [str(e)]

    async def converter(self, origem, destino, callback_status=None, formato="PDF"):
        """Inicia o processo de conversão"""
        try:
            self.parar = False
            return await ConversorModel.converter_para_pdf(
                origem, destino, callback_status, self.parar, formato
            )
        except Exception as e:
            return (0, [str(e)])

    def parar_conversao(self):
        """Para o processo de conversão"""
        self.parar = True

    async def verificar_arquivos_protegidos(self, caminho_arquivo):
        """Verifica se um arquivo está protegido por senha"""
        return await ConversorModel.verificar_arquivo_protegido(caminho_arquivo)

    async def processar_arquivos_protegidos(self, arquivos, pasta_destino, callback_status=None):
        """Processa arquivos protegidos e atualiza o status"""
        self.arquivos_protegidos = arquivos
        self.resultados_protegidos = await ConversorModel.processar_arquivos_protegidos(
            arquivos, pasta_destino, callback_status
        )
        return self.resultados_protegidos

    def obter_relatorio_protegidos(self):
        """Gera um relatório dos arquivos protegidos"""
        if not self.arquivos_protegidos:
            return []

        relatorio = ["\n🔒 Arquivos com senha:"]
        for arquivo in self.arquivos_protegidos[:5]:
            relatorio.append(f"   • {arquivo.name}")
        
        if len(self.arquivos_protegidos) > 5:
            relatorio.append(f"   • ... ({len(self.arquivos_protegidos)-5} arquivos omitidos)")
        
        relatorio.append("   📁 Estes arquivos foram movidos para a pasta: arquivos_com_senha")
        return relatorio

    def obter_estatisticas_protegidos(self):
        """Retorna estatísticas sobre arquivos protegidos"""
        total = len(self.arquivos_protegidos)
        sucessos = sum(1 for _, sucesso, _ in self.resultados_protegidos if sucesso)
        falhas = total - sucessos
        return total, sucessos, falhas

def iniciar_conversao(origem, destino, callback_status=None, formato="PDF"):
    """Função auxiliar para iniciar a conversão em uma thread separada"""
    vm = ConversorViewModel()
    asyncio.run(vm.converter(origem, destino, callback_status, formato))

def iniciar_extracao(origem, callback_status=None):
    """Função auxiliar para iniciar a extração em uma thread separada"""
    vm = ConversorViewModel()
    asyncio.run(vm.extrair_arquivos(origem, callback_status))

def parar_conversao(vm):
    """Função auxiliar para parar a conversão"""
    if vm:
        vm.parar_conversao()

def gerar_relatorio_erros(erros, pasta_destino):
    #Aqui vai gerar um arquivo TXT com erros na pasta de destino
    if not erros:
        return None
        
    try:
        from datetime import datetime
        os.makedirs(pasta_destino, exist_ok=True)
        nome_arquivo = f"erros_conversao_{datetime.now().strftime('%d%m%Y_%H%M%S')}.txt"
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