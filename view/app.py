import flet as ft
import os
from view.ui import criar_interface
from viewmodel.converter_vm import ConversorViewModel

def main(page: ft.Page):

    page.title = "Conversor de Arquivos Versão 2.0.1"

    page.window_width = 400
    page.window_height = 600
    page.window_resizable = False
    page.bgcolor = "#020202"

    #Atualiza a página para aplicar as configurações
    page.update()

    #Inicializa o ViewModel e a interface
    vm = ConversorViewModel()
    page.add(criar_interface(page, vm))

    def on_close(e):
        print("Fechando a aplicação...")
        page.window_destroy()
        os._exit(0)

    #Define o evento de fechamento
    page.on_close = on_close

if __name__ == "__main__":
    ft.app(target=main, assets_dir="assets")
