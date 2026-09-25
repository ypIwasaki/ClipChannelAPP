param([Parameter(Mandatory = $true)][string]$FilePath,
      [ValidateSet('layout', 'subtitles')][string]$Kind = 'layout')

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class ClipChannelLayoutBridge {
    [StructLayout(LayoutKind.Sequential)]
    private struct CopyData {
        public IntPtr dwData;
        public int cbData;
        public IntPtr lpData;
    }

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr FindWindowEx(IntPtr parent, IntPtr after, string className, string title);

    [DllImport("user32.dll", CharSet = CharSet.Unicode, EntryPoint = "SendMessageTimeoutW")]
    private static extern IntPtr SendMessageTimeout(IntPtr window, uint message, IntPtr key,
        ref CopyData data, uint flags, uint timeout, out IntPtr result);

    public static int Apply(string path, string kind) {
        IntPtr data = Marshal.StringToHGlobalUni(path);
        try {
            CopyData packet = new CopyData {
                dwData = new IntPtr(kind == "subtitles" ? 0x43435331 : 0x43434c31),
                cbData = checked((path.Length + 1) * 2),
                lpData = data
            };
            IntPtr previous = IntPtr.Zero;
            while (true) {
                IntPtr window = FindWindowEx(new IntPtr(-3), previous, "ClipChannelLayoutBridge", null);
                if (window == IntPtr.Zero) return 0;
                IntPtr result;
                if (SendMessageTimeout(window, 0x004a, IntPtr.Zero, ref packet, 0x0002, 60000,
                    out result) != IntPtr.Zero && (result.ToInt64() == 1 || result.ToInt64() == 2))
                    return (int)result.ToInt64();
                previous = window;
            }
        } finally {
            Marshal.FreeHGlobal(data);
        }
    }
}
'@

exit [ClipChannelLayoutBridge]::Apply($FilePath, $Kind)
