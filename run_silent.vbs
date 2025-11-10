' VRChat Sugar Checker - 非表示で起動するVBScript
' このスクリプトはコンソールウィンドウを表示せずにPythonスクリプトを実行します

Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' このVBSファイルのディレクトリを取得
strScriptPath = objFSO.GetParentFolderName(WScript.ScriptFullName)

' Pythonスクリプトのパス
strPythonScript = strScriptPath & "\main.py"

' Pythonの実行パスを取得（複数の場所を試行）
strPythonExe = ""

' 1. python3コマンドを試す
strPythonExe = "python3"

' コマンドを構築（サイレントモードで実行）
strCommand = strPythonExe & " """ & strPythonScript & """ --silent"

' ウィンドウを非表示で実行（0 = 非表示、True = 終了を待たない）
objShell.Run strCommand, 0, False

' オブジェクトを解放
Set objShell = Nothing
Set objFSO = Nothing
