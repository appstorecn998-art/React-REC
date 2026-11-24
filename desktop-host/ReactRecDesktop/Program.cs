using System.Diagnostics;
using System.Net.Http;
using System.Text.RegularExpressions;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace ReactRecDesktop;

internal static class Program
{
    private static Process? serverProcess;
    private static readonly string Root = AppContext.BaseDirectory;

    [STAThread]
    private static void Main()
    {
        CleanRecPort();
        ApplicationConfiguration.Initialize();
        using var form = new RecForm();
        Application.Run(form);
        if (serverProcess is { HasExited: false })
        {
            try { serverProcess.Kill(true); } catch { }
        }
        CleanRecPort();
    }

    private static void CleanRecPort()
    {
        try
        {
            using var netstat = Process.Start(new ProcessStartInfo
            {
                FileName = "netstat.exe",
                Arguments = "-ano -p tcp",
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true
            });
            if (netstat == null) return;
            var output = netstat.StandardOutput.ReadToEnd();
            netstat.WaitForExit(3000);
            var pids = new HashSet<int>();
            foreach (var line in output.Split('\n'))
            {
                if (!line.Contains(":8771", StringComparison.OrdinalIgnoreCase) ||
                    !line.Contains("LISTENING", StringComparison.OrdinalIgnoreCase)) continue;
                var match = Regex.Match(line, @"\s(\d+)\s*$");
                if (match.Success && int.TryParse(match.Groups[1].Value, out var pid)) pids.Add(pid);
            }
            foreach (var pid in pids)
            {
                try
                {
                    var process = Process.GetProcessById(pid);
                    if (process.Id != Environment.ProcessId) process.Kill(true);
                }
                catch { }
            }
        }
        catch { }
    }

    internal static async Task StartServerAsync()
    {
        using var client = new HttpClient { Timeout = TimeSpan.FromMilliseconds(700) };
        try
        {
            using var response = await client.GetAsync("http://127.0.0.1:8771/");
            if (response.IsSuccessStatusCode) return;
        }
        catch { }

        var python = File.Exists(@"C:\Users\Fenn\AppData\Local\Python\bin\python.exe")
            ? @"C:\Users\Fenn\AppData\Local\Python\bin\python.exe"
            : "python.exe";
        var logPath = Path.Combine(Root, "output", "desktop-shell-server.log");
        Directory.CreateDirectory(Path.GetDirectoryName(logPath)!);
        serverProcess = Process.Start(new ProcessStartInfo
        {
            FileName = python,
            Arguments = "-B -X utf8 server.py",
            WorkingDirectory = Root,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardError = true,
            RedirectStandardOutput = true
        }) ?? throw new InvalidOperationException("Không khởi động được server REC.");
        _ = serverProcess.StandardError.ReadToEndAsync().ContinueWith(task => File.AppendAllText(logPath, task.Result));

        for (var attempt = 0; attempt < 40; attempt++)
        {
            await Task.Delay(250);
            try
            {
                using var response = await client.GetAsync("http://127.0.0.1:8771/");
                if (response.IsSuccessStatusCode) return;
            }
            catch { }
            if (serverProcess.HasExited) throw new InvalidOperationException("Server REC đã dừng khi khởi động.");
        }
        throw new InvalidOperationException("Server REC chưa sẵn sàng trên cổng 8771.");
    }

    private sealed class RecForm : Form
    {
        private readonly WebView2 webView = new() { Dock = DockStyle.Fill, Visible = false };
        private readonly Panel loadingPanel = new() { Dock = DockStyle.Fill, BackColor = Color.FromArgb(247, 247, 245) };
        private readonly Label loadingTitle = new() { AutoSize = true, Text = "REC Studio", ForeColor = Color.FromArgb(48, 50, 48), Font = new Font("Segoe UI", 19) };
        private readonly Label loadingMessage = new() { AutoSize = true, Text = "Đang khởi động", ForeColor = Color.FromArgb(112, 116, 110), Font = new Font("Segoe UI", 10) };
        private readonly Label loadingMark = new() { AutoSize = true, Text = "◌", ForeColor = Color.FromArgb(112, 116, 110), Font = new Font("Segoe UI", 25) };
        private readonly System.Windows.Forms.Timer loadingTimer = new() { Interval = 360 };
        private int loadingFrame;

        public RecForm()
        {
            Text = "React REC";
            Width = 1440;
            Height = 900;
            MinimumSize = new Size(1000, 650);
            StartPosition = FormStartPosition.CenterScreen;
            loadingPanel.Controls.Add(loadingMessage);
            loadingPanel.Controls.Add(loadingTitle);
            loadingPanel.Controls.Add(loadingMark);
            loadingPanel.Resize += (_, _) => PositionLoading();
            Controls.Add(webView);
            Controls.Add(loadingPanel);
            loadingTimer.Tick += (_, _) =>
            {
                loadingFrame = (loadingFrame + 1) % 4;
                loadingMessage.Text = "Đang khởi động" + new string('.', loadingFrame);
                loadingMark.Text = loadingFrame % 2 == 0 ? "◌" : "○";
            };
            loadingTimer.Start();
            Shown += async (_, _) => await OpenAsync();
        }

        private void PositionLoading()
        {
            loadingMark.Left = (loadingPanel.ClientSize.Width - loadingMark.Width) / 2;
            loadingMark.Top = (loadingPanel.ClientSize.Height - 115) / 2;
            loadingTitle.Left = (loadingPanel.ClientSize.Width - loadingTitle.Width) / 2;
            loadingTitle.Top = loadingMark.Bottom + 10;
            loadingMessage.Left = (loadingPanel.ClientSize.Width - loadingMessage.Width) / 2;
            loadingMessage.Top = loadingTitle.Bottom + 9;
        }

        private async Task OpenAsync()
        {
            try
            {
                await StartServerAsync();
                var userData = Path.Combine(Root, "output", "webview2-user-data");
                Directory.CreateDirectory(userData);
                var environment = await CoreWebView2Environment.CreateAsync(null, userData);
                await webView.EnsureCoreWebView2Async(environment);
                webView.CoreWebView2.Settings.AreDefaultContextMenusEnabled = false;
                webView.CoreWebView2.Settings.AreDevToolsEnabled = false;
                webView.CoreWebView2.Settings.IsStatusBarEnabled = false;
                webView.CoreWebView2.NavigationCompleted += (_, args) =>
                {
                    if (args.IsSuccess)
                    {
                        loadingTimer.Stop();
                        loadingPanel.Visible = false;
                        webView.Visible = true;
                    }
                    else loadingMessage.Text = "Không tải được giao diện React REC.";
                };
                webView.Source = new Uri("http://127.0.0.1:8771/");
            }
            catch (Exception error)
            {
                loadingTimer.Stop();
                loadingMessage.Text = "Không thể mở React REC. " + error.Message;
            }
        }
    }
}
