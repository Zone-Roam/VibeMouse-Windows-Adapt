Option Explicit

Dim fso, shell, scriptDir, projectRoot, pythonwPath, pythonPath, runScript, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
projectRoot = fso.BuildPath(scriptDir, "..")
pythonwPath = fso.BuildPath(projectRoot, ".venv\Scripts\pythonw.exe")
pythonPath = fso.BuildPath(projectRoot, ".venv\Scripts\python.exe")
runScript = fso.BuildPath(scriptDir, "run_tray.py")

If fso.FileExists(pythonwPath) Then
  cmd = """" & pythonwPath & """ """ & runScript & """"
  shell.Run cmd, 0, False
ElseIf fso.FileExists(pythonPath) Then
  cmd = """" & pythonPath & """ """ & runScript & """"
  shell.Run cmd, 0, False
Else
  MsgBox "Python virtual environment not found under .venv\Scripts", vbExclamation, "VibeMouse Tray"
End If
