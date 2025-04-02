import flet as ft
import os
import subprocess
import sys
import threading
from viewmodel.converter_vm import iniciar_conversao, iniciar_extracao, parar_conversao

def criar_interface(page, vm):
    # Cria os FilePicker primeiro
    file_picker_origem = ft.FilePicker()
    file_picker_destino = ft.FilePicker()
    
    # Adiciona ao overlay da página imediatamente
    page.overlay.extend([file_picker_origem, file_picker_destino])

    origem = ft.TextField(label="Selecione a pasta de origem", width=500, read_only=True, bgcolor="#1E1E1E", color="white")
    destino = ft.TextField(label="Selecione a pasta de destino", width=500, read_only=True, bgcolor="#1E1E1E", color="white")
    status = ft.Text("", color="white", text_align="center")
    progresso = ft.Text("", color="white", text_align="center")
    convertendo = ft.Text("⏳ Convertendo:", color="white", visible=False, text_align="center")
    arquivo_atual = ft.Text("", color="white", visible=False, text_align="center")

    def atualizar_origem(path):
        if path:
            origem.value = path
            page.update()

    def atualizar_destino(path):
        if path:
            destino.value = path
        else:
            pasta_padrao = os.path.join(os.path.expanduser("~"), "Desktop", "Convertidos_TIF")
            if not os.path.exists(pasta_padrao):
                os.makedirs(pasta_padrao)
            destino.value = pasta_padrao
        page.update()

    def selecionar_pasta_origem(e):
        file_picker_origem.get_directory_path(dialog_title="Selecione a pasta de origem")

    def selecionar_pasta_destino(e):
        file_picker_destino.get_directory_path(dialog_title="Selecione a pasta de destino")

    # Configura os callbacks dos FilePicker depois que eles já foram criados
    file_picker_origem.on_result = lambda e: atualizar_origem(e.path)
    file_picker_destino.on_result = lambda e: atualizar_destino(e.path)

    def abrir_pasta_destino(e):
        if destino.value:
            if sys.platform == "win32":
                os.startfile(destino.value)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", destino.value])
            else:
                subprocess.Popen(["xdg-open", destino.value])

    def extrair_arquivos(e):
        if not origem.value:
            status.value = "⚠️ Selecione uma pasta de origem!"
        else:
            status.value = ""
            page.update()
            threading.Thread(target=iniciar_extracao, args=(origem.value, atualizar_status)).start()

    #Switch (Botão de alternância)
    formato_saida = ft.Switch(
        value=False,
        on_change=lambda e: page.update(),
        active_color="#C39A7A",
        thumb_color="#FFFFFF"
    )
    
    formato_row = ft.Row([
        ft.Text("Converter para PDF", color="white"),
        formato_saida,
        ft.Text("Converter para TIFF", color="white")
    ],
    alignment=ft.MainAxisAlignment.CENTER,
    spacing=10)

    def converter_arquivos(e):
        if not origem.value or not destino.value:
            status.value = "⚠️ Selecione uma pasta de origem e destino!"
        else:
            status.value = ""
            convertendo.visible = True
            arquivo_atual.visible = True
            progresso.visible = True
            page.update()
            formato = "TIFF" if formato_saida.value else "PDF"  # Define o formato com base no Switch
            threading.Thread(target=iniciar_conversao, args=(origem.value, destino.value, atualizar_status, formato)).start()

    def parar_arquivos(e):
        parar_conversao(vm)
        status.value = "Conversão interrompida pelo usuário."
        convertendo.visible = False
        arquivo_atual.visible = False
        progresso.visible = False
        page.update()

    def atualizar_status(mensagem, erro=None):
        if erro:
            status.value = f"⚠️ {erro}"
        else:
            status.value = mensagem
        
        # Esconde os elementos de progresso ao finalizar
        if mensagem.startswith("✅"):
            convertendo.visible = False
            arquivo_atual.visible = False
            progresso.visible = False
        
        page.update()

    def fechar_janela(e):
        if not hasattr(page, 'fechado'):  #Evita múltiplas chamadas
            page.fechado = True
            print("Fechando a aplicação...")  #Para depuração
            page.window_destroy()
            import sys
            sys.exit()

    page.on_window_close = fechar_janela

    return ft.Column([
        ft.Text("Documenta Planejamento e Microfilmagem", size=24, weight="bold", color="#885E43", text_align="center"),
        ft.Text("Conversor de arquivos para PDF ou para TIFF", size=16, color="#DBD0C5", text_align="center"),
        ft.Divider(color="#DBD0C5"),
        ft.Column([
            origem,
            ft.ElevatedButton("📂 Selecionar pasta de origem", on_click=selecionar_pasta_origem, bgcolor="#303031", color="#DBD0C5"),
            destino,
            ft.ElevatedButton("📂 Selecionar pasta de destino", on_click=selecionar_pasta_destino, bgcolor="#303031", color="#DBD0C5"),
        ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=15),
        
        ft.Column([
            formato_row,
            ft.Row([
                ft.ElevatedButton("📦 Extrair Arquivos ZIP", on_click=extrair_arquivos, bgcolor="#C39A7A", color="#FFFFFF"),
                ft.ElevatedButton("▶️ Converter Arquivos", on_click=converter_arquivos, bgcolor="#C39A7A", color="#FFFFFF"),
                ft.ElevatedButton("⏹️ Parar", on_click=parar_arquivos, bgcolor="#C39A7A", color="#FFFFFF"),
                ft.ElevatedButton("📁 Abrir pasta de destino", on_click=abrir_pasta_destino, bgcolor="#C39A7A", color="#FFFFFF"),
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=15),
        ], alignment=ft.MainAxisAlignment.CENTER, spacing=10),
        
        convertendo,
        arquivo_atual,
        progresso,
        status
    ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=20)