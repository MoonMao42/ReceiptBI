## 下载 / Downloads

| 平台 / Platform | 文件 / File |
|---|---|
| macOS Apple 芯片 / Apple silicon | `mac-arm64.dmg` |
| macOS Intel 芯片 / Intel | `mac-x64.dmg` |
| Windows x64 | `win-x64.exe` |

ZIP 是 DMG 之外的备用下载格式。ZIP is available as an alternative to the DMG.

## 安装 / Installation

打开 DMG 后，将 ReceiptBI 拖入“应用程序”。如果发布说明标注当前构建未签名，且系统阻止首次打开，请运行：

After opening the DMG, move ReceiptBI to Applications. If the release is marked as unsigned and macOS blocks the first launch, run:

```bash
xattr -cr /Applications/ReceiptBI.app
```

Windows 用户可直接运行 `.exe` 安装程序。

On Windows, run the `.exe` installer.

## 校验 / Verify

下载 `SHA256SUMS` 后，计算你所下载安装包的 SHA-256，并与文件中的同名记录比对。

Download `SHA256SUMS`, calculate the SHA-256 of the installer you downloaded, and compare it with the matching entry.

```bash
# macOS
shasum -a 256 ReceiptBI-*.dmg

# macOS ZIP
shasum -a 256 ReceiptBI-*.zip
```

```powershell
# Windows PowerShell
Get-FileHash .\ReceiptBI-*-win-x64.exe -Algorithm SHA256
```
