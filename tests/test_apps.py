from sayso.apps import App, build_list, find_app, match_foreground

START = [
    {"n": "Google Chrome", "id": "Chrome"},
    {"n": "Visual Studio Code", "id": "Microsoft.VisualStudioCode"},
    {"n": "Uninstall Visual Studio Code", "id": "{6D809377}\\Microsoft VS Code\\unins000.exe"},
    {"n": "Calculator", "id": "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"},
    {"n": "Notepad", "id": "{1AC14E77}\\notepad.exe"},
    {"n": "Python 3.11 Manuals", "id": "{7C5A40EF}\\Python311\\Doc\\python311.chm"},
    {"n": "Zoom Website", "id": "https://zoom.us"},
    {"n": "Word", "id": "Microsoft.Office.WINWORD.EXE.15"},
    {"n": "Excel", "id": "Microsoft.Office.EXCEL.EXE.15"},
    {"n": "Google Chrome", "id": "Chrome"},  # duplicate
    {"n": "Terminal", "id": "Microsoft.WindowsTerminal_8wekyb3d8bbwe!App"},
]
LNK = [
    {"n": "Google Chrome", "t": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"},
    {"n": "Visual Studio Code", "t": "C:\\Users\\sunny\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe"},
    {"n": "Word", "t": "C:\\Program Files\\Microsoft Office\\root\\Office16\\WINWORD.EXE"},
    {"n": "Excel", "t": "C:\\Program Files\\Microsoft Office\\root\\Office16\\EXCEL.EXE"},
]


def apps():
    return build_list(START, LNK)


def test_build_list_filters_junk_and_dupes():
    names = [a.name for a in apps()]
    assert names == ["Calculator", "Excel", "Google Chrome", "Notepad", "Terminal", "Visual Studio Code", "Word"]


def test_exe_names_known():
    by = {a.name: a for a in apps()}
    assert by["Google Chrome"].exe == "chrome.exe"
    assert by["Visual Studio Code"].exe == "code.exe"
    assert by["Notepad"].exe == "notepad.exe"          # from the AppID path
    assert by["Calculator"].exe == "" and by["Calculator"].is_store_app


def test_foreground_by_exe():
    a = match_foreground(apps(), r"C:\Program Files\Google\Chrome\Application\chrome.exe", "Inbox - Gmail")
    assert a.name == "Google Chrome"


def test_foreground_store_app_by_title():
    a = match_foreground(apps(), r"C:\Windows\System32\ApplicationFrameHost.exe", "Calculator")
    assert a.name == "Calculator"


def test_foreground_unknown_app():
    assert match_foreground(apps(), r"C:\Tools\weird.exe", "Untitled") is None


def test_find_app_by_voice():
    a = apps()
    assert find_app(a, "chrome").name == "Google Chrome"
    assert find_app(a, "Chrome").name == "Google Chrome"
    assert find_app(a, "vs code").name == "Visual Studio Code"
    assert find_app(a, "calculator").name == "Calculator"
    assert find_app(a, "notepad").name == "Notepad"
    assert find_app(a, "word").name == "Word"
    assert find_app(a, "photoshop") is None


def test_handles_empty_input():
    assert build_list([], []) == []
    assert build_list(None, None) == []
