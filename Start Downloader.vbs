Option Explicit
Dim shell, files, folder, python, command
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
folder = files.GetParentFolderName(WScript.ScriptFullName)
python = files.BuildPath(folder, "venv\Scripts\pythonw.exe")
If Not files.FileExists(python) Then
    MsgBox "The project's Python environment is missing. Please follow the setup steps in readme.md first.", 48, "Streamline setup"
    WScript.Quit 1
End If
shell.CurrentDirectory = folder
command = Chr(34) & python & Chr(34) & " " & Chr(34) & files.BuildPath(folder, "gui.py") & Chr(34)
shell.Run command, 0, False
