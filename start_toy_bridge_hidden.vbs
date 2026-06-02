Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
command = """" & fso.BuildPath(scriptDir, "start_toy_bridge_background.bat") & """"
shell.Run command, 0, False
