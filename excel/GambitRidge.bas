Attribute VB_Name = "GambitRidge"
' Gambit Ridge Capital - complement Excel : BDP, BDH, BDS, BQL avec la syntaxe Bloomberg.
' Les fonctions interrogent le terminal Gambit Ridge (/api/xl). Windows : MSXML2 ; Mac : AppleScriptTask
' (script GambitRidge.scpt dans ~/Library/Application Scripts/com.microsoft.Excel/, installe par installer_mac.sh).
' Adresse du terminal : macro GRC_Configurer (par defaut http://127.0.0.1:8765, le tunnel du Mac).
Option Explicit

Private Const APPLI As String = "GambitRidge"
Private Const DUREE_CACHE As Double = 60# / 86400#   ' une minute, en jours
Private mCache As Collection

' ------------------------------------------------------------------ fonctions de feuille

Public Function BDP(Security As Variant, Field As Variant, ParamArray Overrides() As Variant) As Variant
    BDP = Scalaire(Appeler("bdp", "s=" & Enc(Texte(Security)) & "&f=" & Enc(Texte(Field))))
End Function

Public Function BDH(Security As Variant, Fields As Variant, StartDate As Variant, ParamArray Rest() As Variant) As Variant
    Dim fin As String, opts As String, debut As Long
    debut = LBound(Rest)
    If UBound(Rest) >= debut Then
        If InStr(Texte(Rest(debut)), "=") = 0 Then fin = DateBbg(Rest(debut)): debut = debut + 1
    End If
    opts = Options(Rest, debut)
    BDH = Appeler("bdh", "s=" & Enc(Texte(Security)) & "&f=" & Enc(Liste(Fields)) & "&d=" & Enc(DateBbg(StartDate)) & _
                  "&e=" & Enc(fin) & "&o=" & Enc(opts))
End Function

Public Function BDS(Security As Variant, Field As Variant, ParamArray Opts() As Variant) As Variant
    BDS = Appeler("bds", "s=" & Enc(Texte(Security)) & "&f=" & Enc(Texte(Field)) & "&o=" & Enc(Options(Opts, LBound(Opts))))
End Function

Public Function BQL(Universe As Variant, ParamArray Rest() As Variant) As Variant
    Dim expr As String, params As String, i As Long
    If UBound(Rest) >= LBound(Rest) Then expr = Texte(Rest(LBound(Rest)))
    For i = LBound(Rest) + 1 To UBound(Rest)
        If Len(Texte(Rest(i))) > 0 Then params = params & IIf(Len(params) > 0, "|", "") & Texte(Rest(i))
    Next i
    BQL = Appeler("bql", "u=" & Enc(Texte(Universe)) & "&x=" & Enc(expr) & "&o=" & Enc(params))
End Function

' ------------------------------------------------------------------ macros

Public Sub GRC_Configurer()
    Dim v As String
    v = InputBox("Adresse du terminal Gambit Ridge (Mac : http://127.0.0.1:8765 ; autre poste : son adresse Tailscale)", _
                 "Gambit Ridge", Serveur())
    If Len(v) > 0 Then SaveSetting APPLI, "Excel", "Serveur", v
    Set mCache = Nothing
End Sub

Public Sub GRC_Installer()
    ' copie le complement dans le dossier des complements d'Excel et l'active (charge a chaque demarrage)
    Dim a As Object
    Set a = Application.AddIns.Add(ThisWorkbook.FullName, True)
    a.Installed = True
End Sub

Public Sub GRC_Actualiser()
    ' equivalent du bouton Refresh de Bloomberg : vide le cache et recalcule tout
    Set mCache = Nothing
    Application.CalculateFull
End Sub

' ------------------------------------------------------------------ transport

Private Function Serveur() As String
    Serveur = GetSetting(APPLI, "Excel", "Serveur", "http://127.0.0.1:8765")
End Function

Private Function Appeler(fn As String, requete As String) As Variant
    Dim url As String, rep As String
    url = Serveur() & "/api/xl?fn=" & fn & "&" & requete
    rep = Recuperer(url)
    Appeler = Tableau(rep)
End Function

Private Function Recuperer(url As String) As String
    Dim t As Variant
    If mCache Is Nothing Then Set mCache = New Collection
    On Error Resume Next
    t = mCache(url)
    If Err.Number = 0 Then
        If Now - t(0) < DUREE_CACHE Then Recuperer = t(1): Exit Function
        mCache.Remove url
    End If
    Err.Clear
    On Error GoTo echec
#If Mac Then
    Recuperer = AppleScriptTask("GambitRidge.scpt", "recuperer", url)
#Else
    Dim h As Object
    Set h = CreateObject("MSXML2.ServerXMLHTTP.6.0")
    h.setTimeouts 5000, 5000, 30000, 60000
    h.Open "GET", url, False
    h.send
    Recuperer = h.responseText
#End If
    If Len(Recuperer) = 0 Then Recuperer = "#N/A Terminal injoignable (" & Serveur() & ")"
    If Left$(LTrim$(Recuperer), 1) = "<" Then Recuperer = "#N/A Terminal sans /api/xl (a mettre a jour)"
    If Left$(Recuperer, 4) <> "#N/A" Or InStr(Recuperer, "injoignable") = 0 Then mCache.Add Array(Now, Recuperer), url
    Exit Function
echec:
    Recuperer = "#N/A Terminal injoignable (" & Serveur() & ")"
End Function

' ------------------------------------------------------------------ lecture de la reponse (TSV)

Private Function Tableau(rep As String) As Variant
    Dim lignes() As String, cols() As String, n As Long, m As Long, i As Long, j As Long, out() As Variant
    rep = Replace(rep, vbCr, "")
    If Right$(rep, 1) = vbLf Then rep = Left$(rep, Len(rep) - 1)
    lignes = Split(rep, vbLf)
    n = UBound(lignes) + 1
    For i = 0 To n - 1
        cols = Split(lignes(i), vbTab)
        If UBound(cols) + 1 > m Then m = UBound(cols) + 1
    Next i
    If n = 1 And m <= 1 Then Tableau = Valeur(lignes(0)): Exit Function
    ReDim out(1 To n, 1 To m)
    For i = 0 To n - 1
        cols = Split(lignes(i), vbTab)
        For j = 0 To m - 1
            If j <= UBound(cols) Then out(i + 1, j + 1) = Valeur(cols(j)) Else out(i + 1, j + 1) = ""
        Next j
    Next i
    Tableau = out
End Function

Private Function Scalaire(v As Variant) As Variant
    If IsArray(v) Then Scalaire = v(1, 1) Else Scalaire = v
End Function

Private Function Valeur(s As String) As Variant
    ' nombres au format 1.5E-3 (independant de la langue d'Excel), dates AAAA-MM-JJ, booleens, texte
    If Len(s) = 0 Then Valeur = "": Exit Function
    If s Like "####-##-##" Then Valeur = DateSerial(CInt(Left$(s, 4)), CInt(Mid$(s, 6, 2)), CInt(Right$(s, 2))): Exit Function
    If s = "TRUE" Then Valeur = True: Exit Function
    If s = "FALSE" Then Valeur = False: Exit Function
    If Not s Like "*[!0-9.E+-]*" And s Like "*#*" Then Valeur = Val(s): Exit Function
    Valeur = s
End Function

' ------------------------------------------------------------------ arguments

Private Function Texte(v As Variant) As String
    If TypeName(v) = "Range" Then v = v.Cells(1, 1).Value
    If IsError(v) Or IsEmpty(v) Then Texte = "": Exit Function
    If IsArray(v) Then Texte = Liste(v): Exit Function
    If VarType(v) = vbDouble Or VarType(v) = vbSingle Or VarType(v) = vbLong Or VarType(v) = vbInteger Then
        Texte = Replace(CStr(v), Application.International(xlDecimalSeparator), ".")
    Else
        Texte = CStr(v)
    End If
End Function

Private Function Liste(v As Variant) As String
    ' champs passes en plage (A1:C1) ou en tableau ({"PX_LAST","PX_VOLUME"}) -> "PX_LAST,PX_VOLUME"
    Dim c As Variant, s As String
    If TypeName(v) = "Range" Then
        For Each c In v.Cells
            If Len(CStr(c.Value)) > 0 Then s = s & IIf(Len(s) > 0, ",", "") & CStr(c.Value)
        Next c
    ElseIf IsArray(v) Then
        For Each c In v
            If Len(CStr(c)) > 0 Then s = s & IIf(Len(s) > 0, ",", "") & CStr(c)
        Next c
    Else
        s = CStr(v)
    End If
    Liste = s
End Function

Private Function DateBbg(v As Variant) As String
    ' date Excel -> AAAAMMJJ ; texte ("-1Y", "20240101", "") transmis tel quel
    If TypeName(v) = "Range" Then v = v.Cells(1, 1).Value
    If IsEmpty(v) Then DateBbg = "": Exit Function
    If VarType(v) = vbDate Then DateBbg = Format$(v, "yyyymmdd"): Exit Function
    If IsNumeric(v) And VarType(v) <> vbString Then
        If v > 20000 And v < 80000 Then DateBbg = Format$(CDate(v), "yyyymmdd"): Exit Function
    End If
    DateBbg = CStr(v)
End Function

Private Function Options(ByVal arr As Variant, ByVal debut As Long) As String
    ' "Per=W", "Dts=H" ... ou paires ("Per", "W") -> "Per=W|Dts=H"
    Dim i As Long, s As String, a As String
    i = debut
    Do While i <= UBound(arr)
        a = Texte(arr(i))
        If InStr(a, "=") > 0 Then
            s = s & IIf(Len(s) > 0, "|", "") & a
        ElseIf Len(a) > 0 And i < UBound(arr) Then
            s = s & IIf(Len(s) > 0, "|", "") & a & "=" & Texte(arr(i + 1))
            i = i + 1
        End If
        i = i + 1
    Loop
    Options = s
End Function

Private Function Enc(s As String) As String
    ' encodage URL en UTF-8 (ENCODEURL n'existe pas dans Excel pour Mac)
    Dim i As Long, c As Long, r As String
    For i = 1 To Len(s)
        c = AscW(Mid$(s, i, 1)) And &HFFFF&
        If (c >= 48 And c <= 57) Or (c >= 65 And c <= 90) Or (c >= 97 And c <= 122) Or c = 45 Or c = 46 Or c = 95 Or c = 126 Then
            r = r & ChrW(c)
        ElseIf c < &H80& Then
            r = r & "%" & Right$("0" & Hex(c), 2)
        ElseIf c < &H800& Then
            r = r & "%" & Hex(&HC0& Or (c \ &H40&)) & "%" & Hex(&H80& Or (c And &H3F&))
        Else
            r = r & "%" & Hex(&HE0& Or (c \ &H1000&)) & "%" & Hex(&H80& Or ((c \ &H40&) And &H3F&)) & "%" & Hex(&H80& Or (c And &H3F&))
        End If
    Next i
    Enc = r
End Function
