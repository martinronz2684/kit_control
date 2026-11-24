; Setup für Sintratec Central: Drucken über den Kit Control (Pi) per WLAN oder USB-Netzwerk.
; Tauscht nur die USB-Bibliothek usb4java-1.2.0.jar in Central aus und sichert das Original.
; Deinstallieren (Windows: Einstellungen > Apps) stellt das Original wieder her.
; Bauen: ISCC.exe /DVer=1.0.0 KitControlCentral.iss  (die neue usb4java-1.2.0.jar liegt in ..\)

#ifndef Ver
  #define Ver "1.0.0"
#endif
#define Jar "usb4java-1.2.0.jar"

[Setup]
AppId={{6E2B6F3A-6C1D-4E59-9C1B-2F4B7A0D5C11}
AppName=Kit Control für Sintratec Central
AppVersion={#Ver}
AppPublisher=Kit Control
DefaultDirName={localappdata}\KitControl\Central
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=KitControl-Central-Setup
SetupIconFile=kitcontrol.ico
UninstallDisplayIcon={app}\kitcontrol.ico
UninstallDisplayName=Kit Control für Sintratec Central
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
CloseApplications=no

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"

[Files]
Source: "..\{#Jar}"; DestDir: "{app}"; Flags: ignoreversion
Source: "kitcontrol.ico"; DestDir: "{app}"; Flags: ignoreversion

[Code]
var
  LibPage: TInputDirWizardPage;
  IpPage: TInputQueryWizardPage;

function StateFile: String;
begin
  Result := ExpandConstant('{app}\install.ini');
end;

function CfgFile: String;
begin
  Result := ExpandConstant('{%USERPROFILE}\kit-control.txt');
end;

{ Ordner app\lib von Central suchen }
function FindLib: String;
var
  C: array of String;
  I: Integer;
begin
  Result := '';
  SetArrayLength(C, 4);
  C[0] := ExpandConstant('{localappdata}\Sintratec\Central64\app\lib');
  C[1] := ExpandConstant('{localappdata}\Sintratec\Central\app\lib');
  C[2] := ExpandConstant('{commonpf64}\Sintratec\Central64\app\lib');
  C[3] := ExpandConstant('{commonpf32}\Sintratec\Central\app\lib');
  for I := 0 to GetArrayLength(C) - 1 do
    if FileExists(C[I] + '\{#Jar}') then begin
      Result := C[I];
      Exit;
    end;
end;

{ Läuft Central, ist die Bibliothek gesperrt und lässt sich nicht umbenennen }
function JarLocked(const Lib: String): Boolean;
var
  T, P: String;
begin
  T := Lib + '\{#Jar}';
  P := T + '.probe';
  Result := False;
  if not FileExists(T) then Exit;
  if RenameFile(T, P) then
    RenameFile(P, T)
  else
    Result := True;
end;

procedure InitializeWizard;
var
  Found: String;
begin
  Found := FindLib;
  LibPage := CreateInputDirPage(wpWelcome, 'Sintratec Central',
    'Wo ist Central installiert?',
    'Ordner "app\lib" von Sintratec Central (enthält {#Jar}). ' +
    'Normalerweise wird er automatisch gefunden.', False, '');
  LibPage.Add('');
  LibPage.Values[0] := Found;

  IpPage := CreateInputQueryPage(LibPage.ID, 'Verbindung zum Pi',
    'Wie findet Central den Kit Control?',
    'Leer lassen: Central sucht den Pi automatisch im WLAN (bzw. per USB-Kabel unter 10.55.0.1). ' +
    'Nur wenn das nicht klappt, die IP-Adresse eintragen, die am Display unter System steht.');
  IpPage.Add('Feste IP-Adresse (optional):', False);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Lib: String;
begin
  Result := True;
  if CurPageID = LibPage.ID then begin
    Lib := RemoveBackslashUnlessRoot(LibPage.Values[0]);
    if not FileExists(Lib + '\{#Jar}') then begin
      MsgBox('In diesem Ordner liegt keine {#Jar}. Bitte den Ordner "app\lib" von Sintratec Central wählen.', mbError, MB_OK);
      Result := False;
    end else if JarLocked(Lib) then begin
      MsgBox('Sintratec Central läuft noch. Bitte Central schließen und dann auf "Weiter" klicken.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Lib, Target, Backup, Ours, Ip: String;
begin
  if CurStep <> ssPostInstall then Exit;
  Lib := RemoveBackslashUnlessRoot(LibPage.Values[0]);
  Target := Lib + '\{#Jar}';
  Backup := Target + '.original';
  Ours := ExpandConstant('{app}\{#Jar}');

  { Ist die Datei in Central nicht unsere, ist sie das Original (auch nach einem Central-Update) -> sichern }
  if GetSHA1OfFile(Target) <> GetSHA1OfFile(Ours) then begin
    if not FileCopy(Target, Backup, False) then
      RaiseException('Original konnte nicht gesichert werden: ' + Backup);
    ForceDirectories(ExpandConstant('{app}\original'));
    FileCopy(Target, ExpandConstant('{app}\original\{#Jar}'), False);
  end;
  if not FileExists(Backup) and not FileExists(ExpandConstant('{app}\original\{#Jar}')) then
    RaiseException('Kein Original vorhanden – die Bibliothek in Central ist bereits ausgetauscht, aber ohne Sicherung. Bitte Central neu installieren und das Setup erneut ausführen.');
  if not FileCopy(Ours, Target, False) then
    RaiseException('Bibliothek konnte nicht ersetzt werden. Läuft Central noch?');

  Ip := Trim(IpPage.Values[0]);
  if Ip <> '' then
    SaveStringToFile(CfgFile, 'host=' + Ip + #13#10, False)
  else if FileExists(CfgFile) then
    DeleteFile(CfgFile);

  SetIniString('install', 'lib', Lib, StateFile);
end;

{ ---- Deinstallation: Original wiederherstellen ---- }
function InitializeUninstall: Boolean;
var
  Lib: String;
begin
  Result := True;
  Lib := GetIniString('install', 'lib', '', StateFile);
  while (Lib <> '') and JarLocked(Lib) do begin
    if MsgBox('Sintratec Central läuft noch. Bitte Central schließen und auf OK klicken.', mbError, MB_OKCANCEL) = IDCANCEL then begin
      Result := False;
      Exit;
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Lib, Target, Backup, Saved: String;
begin
  if CurUninstallStep <> usUninstall then Exit;
  Lib := GetIniString('install', 'lib', '', StateFile);
  if Lib = '' then Exit;
  Target := Lib + '\{#Jar}';
  Backup := Target + '.original';
  Saved := ExpandConstant('{app}\original\{#Jar}');
  if FileExists(Backup) then begin
    if FileCopy(Backup, Target, False) then DeleteFile(Backup)
    else MsgBox('Original konnte nicht zurückkopiert werden. Es liegt hier: ' + Backup, mbError, MB_OK);
  end else if FileExists(Saved) then
    FileCopy(Saved, Target, False)
  else
    MsgBox('Keine Sicherung des Originals gefunden. Bitte Sintratec Central neu installieren.', mbError, MB_OK);
  if FileExists(CfgFile) then DeleteFile(CfgFile);
  DeleteFile(Saved);
  RemoveDir(ExpandConstant('{app}\original'));
  DeleteFile(StateFile);
end;
