Sub ExportDashboardAsPDF()
    ' VBA Script to export MUMMA Dashboard as PDF
    ' Run this in Excel after opening MUMMA MASTER 2425.xlsx
    
    Dim ws As Worksheet
    Dim outputPath As String
    Dim fileName As String
    Dim fullPath As String
    
    ' Set the worksheet to DASH
    Set ws = ThisWorkbook.Worksheets("DASH")
    
    ' Check if DASH sheet exists
    If ws Is Nothing Then
        MsgBox "DASH sheet not found!", vbExclamation
        Exit Sub
    End If
    
    ' Set output path (adjust for Mac path)
    outputPath = "/Users/davidcraig/Dropbox (Personal)/CLOVE/CLIENTS/MUMMA/"
    fileName = "mumma_dashboard.pdf"
    
    ' For Mac, we'll use a different approach since direct PDF export might not work
    ' We'll copy to a new sheet and format it nicely
    
    ' Create a new workbook for export
    Dim exportWB As Workbook
    Set exportWB = Workbooks.Add
    
    ' Copy data from A1:AA61
    Dim dataRange As Range
    Set dataRange = ws.Range("A1:AA61")
    
    ' Copy data to new workbook
    dataRange.Copy
    exportWB.Worksheets(1).Range("A1").PasteSpecial xlPasteValues
    exportWB.Worksheets(1).Range("A1").PasteSpecial xlPasteFormats
    
    ' Rename the sheet
    exportWB.Worksheets(1).Name = "MUMMA Dashboard"
    
    ' Format the sheet nicely
    With exportWB.Worksheets(1)
        ' Auto-fit columns
        .Columns("A:Z").AutoFit
        
        ' Add a title
        .Range("A1").Font.Size = 16
        .Range("A1").Font.Bold = True
        .Range("A1").Font.Color = RGB(46, 134, 171) ' MUMMA blue
        
        ' Format header row
        .Range("A1:Z1").Font.Bold = True
        .Range("A1:Z1").Interior.Color = RGB(46, 134, 171)
        .Range("A1:Z1").Font.Color = RGB(255, 255, 255)
        
        ' Add borders
        .Range("A1:Z61").Borders.LineStyle = xlContinuous
        .Range("A1:Z61").Borders.Weight = xlThin
        
        ' Alternate row colors for readability
        Dim i As Integer
        For i = 2 To 61 Step 2
            .Range("A" & i & ":Z" & i).Interior.Color = RGB(248, 249, 250)
        Next i
    End With
    
    ' Try to save as PDF (Mac compatible)
    On Error Resume Next
    
    ' Method 1: Try direct PDF export
    fullPath = outputPath & fileName
    exportWB.ExportAsFixedFormat Type:=xlTypePDF, Filename:=fullPath
    
    If Err.Number = 0 Then
        MsgBox "Dashboard exported as PDF successfully to:" & vbCrLf & fullPath, vbInformation
    Else
        ' Method 2: Save as Excel and provide instructions
        Dim excelPath As String
        excelPath = outputPath & "mumma_dashboard_export.xlsx"
        exportWB.SaveAs excelPath
        
        MsgBox "PDF export failed. Dashboard saved as Excel file:" & vbCrLf & excelPath & vbCrLf & vbCrLf & _
               "To create PDF:" & vbCrLf & _
               "1. Open the saved Excel file" & vbCrLf & _
               "2. File → Export → Create PDF" & vbCrLf & _
               "3. Save as 'mumma_dashboard.pdf' in the same folder", vbInformation
    End If
    
    On Error GoTo 0
    
    ' Close export workbook
    exportWB.Close False
    
    ' Clean up
    Application.CutCopyMode = False
End Sub

Sub ExportDashboardSimple()
    ' Simpler version - just copy and format for manual PDF export
    Dim ws As Worksheet
    
    ' Set the worksheet to DASH
    Set ws = ThisWorkbook.Worksheets("DASH")
    
    ' Check if DASH sheet exists
    If ws Is Nothing Then
        MsgBox "DASH sheet not found!", vbExclamation
        Exit Sub
    End If
    
    ' Create a new workbook
    Dim exportWB As Workbook
    Set exportWB = Workbooks.Add
    
    ' Copy data from A1:AA61
    Dim dataRange As Range
    Set dataRange = ws.Range("A1:AA61")
    
    ' Copy data to new workbook
    dataRange.Copy
    exportWB.Worksheets(1).Range("A1").PasteSpecial xlPasteValues
    exportWB.Worksheets(1).Range("A1").PasteSpecial xlPasteFormats
    
    ' Rename sheet
    exportWB.Worksheets(1).Name = "MUMMA Dashboard"
    
    ' Format nicely
    With exportWB.Worksheets(1)
        .Columns("A:Z").AutoFit
        .Range("A1").Font.Size = 16
        .Range("A1").Font.Bold = True
        .Range("A1:Z1").Font.Bold = True
        .Range("A1:Z1").Interior.Color = RGB(46, 134, 171)
        .Range("A1:Z1").Font.Color = RGB(255, 255, 255)
        .Range("A1:Z61").Borders.LineStyle = xlContinuous
    End With
    
    MsgBox "Dashboard copied and formatted!" & vbCrLf & vbCrLf & _
           "To create PDF:" & vbCrLf & _
           "1. File → Export → Create PDF" & vbCrLf & _
           "2. Save as 'mumma_dashboard.pdf'" & vbCrLf & _
           "3. Place in your MUMMA folder", vbInformation
End Sub 