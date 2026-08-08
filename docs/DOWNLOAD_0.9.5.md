# 0.9.5 下载说明

GitHub Release 为避免单个资产超过当前网络链路限制，安装包和便携包各提供两个分卷。

## 安装包

下载以下两个文件到同一目录：

- `ShandongQuotaAssistant-Setup-0.9.5.exe.001`
- `ShandongQuotaAssistant-Setup-0.9.5.exe.002`

在该目录打开 PowerShell，执行：

```powershell
cmd /c copy /b ShandongQuotaAssistant-Setup-0.9.5.exe.001+ShandongQuotaAssistant-Setup-0.9.5.exe.002 ShandongQuotaAssistant-Setup-0.9.5.exe
```

然后双击生成的 `ShandongQuotaAssistant-Setup-0.9.5.exe`。

## 便携版

下载以下两个文件到同一目录，用同样的方式合并：

```powershell
cmd /c copy /b ShandongQuotaAssistant-Portable-0.9.5.7z.001+ShandongQuotaAssistant-Portable-0.9.5.7z.002 ShandongQuotaAssistant-Portable-0.9.5.7z
```

再用 7-Zip 打开生成的 `.7z` 文件。`SHA256SUMS.txt` 用于校验合并后的完整文件。
