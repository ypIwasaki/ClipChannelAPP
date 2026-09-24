// AviUtl2 plugin: append editable text objects from a ClipChannel subtitle file.
#include <windows.h>
#include <commdlg.h>
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include "plugin2.h"

static EDIT_HANDLE* edit_handle = nullptr;
static COMMON_PLUGIN_TABLE plugin_table = {L"ClipChannel Subtitle Import", L"Add editable subtitles from ClipChannelAPP"};
struct Caption { int first, last; std::string text; };
static std::vector<Caption> captions;
static int imported, rejected;
static std::filesystem::path selected_file;
static bool matching_project;
static std::string video_path;

static bool decode_hex(const std::string& value, std::string& output) {
    if (value.size() % 2) return false;
    output.clear();
    for (size_t i = 0; i < value.size(); i += 2) {
        auto hex = [](char c) -> int {
            if (c >= '0' && c <= '9') return c - '0';
            if (c >= 'a' && c <= 'f') return c - 'a' + 10;
            return -1;
        };
        int high = hex(value[i]), low = hex(value[i + 1]);
        if (high < 0 || low < 0) return false;
        output.push_back(static_cast<char>((high << 4) | low));
    }
    return true;
}

static bool read_captions(const wchar_t* path) {
    std::ifstream file(std::filesystem::path(path), std::ios::binary);
    std::string line;
    if (!std::getline(file, line) || line != "ClipChannel-Subtitles-1") return false;
    if (!std::getline(file, line) || line.rfind("video\t", 0) != 0 ||
        !decode_hex(line.substr(6), video_path)) return false;
    if (!std::getline(file, line) || line.rfind("count\t", 0) != 0) return false;
    int count;
    try { count = std::stoi(line.substr(6)); } catch (...) { return false; }
    if (count < 0 || count > 10000) return false;
    std::vector<Caption> parsed;
    for (int i = 0; i < count; ++i) {
        if (!std::getline(file, line)) return false;
        auto a = line.find('\t'), b = line.find('\t', a + 1);
        if (a == std::string::npos || b == std::string::npos) return false;
        Caption row;
        try {
            row.first = std::stoi(line.substr(0, a));
            row.last = std::stoi(line.substr(a + 1, b - a - 1));
        } catch (...) { return false; }
        if (row.first < 0 || row.last < row.first || !decode_hex(line.substr(b + 1), row.text)) return false;
        parsed.push_back(std::move(row));
    }
    if (std::getline(file, line)) return false;
    captions = std::move(parsed);
    return true;
}

static std::string alias_for(const std::string& text) {
    std::string escaped;
    for (size_t i = 0; i < text.size(); ++i) {
        if (text[i] == '\r') {
            if (i + 1 < text.size() && text[i + 1] == '\n') ++i;
            escaped += "\\n";
        } else if (text[i] == '\n') escaped += "\\n";
        else escaped += text[i];
    }
    return "[Object]\r\nframe=0,0\r\n[Object.0]\r\neffect.name=テキスト\r\n"
           "サイズ=40.00\r\n字間=0.00\r\n行間=0.00\r\n表示速度=0.00\r\n"
           "フォント=Yu Gothic UI\r\n文字色=ffffff\r\n影・縁色=000000\r\n"
           "文字装飾=標準文字\r\n文字揃え=中央揃え[下]\r\nB=0\r\nI=0\r\n"
           "テキスト=" + escaped + "\r\n文字毎に個別オブジェクト=0\r\n"
           "自動スクロール=0\r\n移動座標上に表示=0\r\n"
           "オブジェクトの長さを自動調節=0\r\n[Object.1]\r\n"
           "effect.name=標準描画\r\nX=0.00\r\nY=350.00\r\nZ=0.00\r\n"
           "拡大率=100.000\r\n縦横比=0.000\r\n透明度=0.00\r\n合成モード=通常\r\n";
}

static void create_objects(EDIT_SECTION* edit) {
    imported = rejected = 0;
    auto project = edit->get_project_file(edit_handle);
    auto path = project ? project->get_project_file_path() : nullptr;
    matching_project = path && std::filesystem::path(path).parent_path() == selected_file.parent_path();
    std::replace(video_path.begin(), video_path.end(), '\\', '/');
    bool video_found = false;
    for (int layer = 0; matching_project && layer < 32 && !video_found; ++layer) {
        auto object = edit->find_object(layer, 0);
        auto alias = object ? edit->get_object_alias(object) : nullptr;
        if (alias && std::string(alias).find("ファイル=" + video_path + "\r\n") != std::string::npos)
            video_found = true;
    }
    matching_project = matching_project && video_found;
    if (!matching_project) return;
    for (const auto& row : captions) {
        int layer = 2;
        for (; layer < 512; ++layer) {
            bool free = true;
            for (int frame = row.first; frame <= row.last; ++frame) {
                if (edit->find_object(layer, frame)) { free = false; break; }
            }
            if (free) break;
        }
        if (layer == 512) { ++rejected; continue; }
        auto alias = alias_for(row.text);
        if (edit->create_object_from_alias(alias.c_str(), layer, row.first, row.last - row.first + 1))
            ++imported;
        else ++rejected;
    }
}

static void import_menu(void*) {
    wchar_t filename[32768] = L"";
    OPENFILENAMEW dialog{};
    dialog.lStructSize = sizeof(dialog);
    dialog.lpstrFilter = L"ClipChannel subtitles (*.ccsub)\0*.ccsub\0\0";
    dialog.lpstrFile = filename;
    dialog.nMaxFile = 32768;
    dialog.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST;
    if (!GetOpenFileNameW(&dialog)) return;
    if (!read_captions(filename)) {
        MessageBoxW(nullptr, L"字幕ファイルを読み取れません", L"ClipChannel", MB_ICONERROR);
        return;
    }
    selected_file = std::filesystem::path(filename);
    if (!edit_handle->call_edit_section(create_objects)) {
        MessageBoxW(nullptr, L"編集セクションを開始できません", L"ClipChannel", MB_ICONERROR);
        return;
    }
    if (!matching_project) {
        MessageBoxW(nullptr, L"対応する編集フォルダへプロジェクトを保存し、編集用動画を先頭に配置してから追加してください", L"ClipChannel", MB_ICONERROR);
        return;
    }
    auto message = std::to_wstring(imported) + L" 件を追加しました。";
    if (rejected) message += L" " + std::to_wstring(rejected) + L" 件を追加できませんでした。";
    MessageBoxW(nullptr, message.c_str(), L"ClipChannel", rejected ? MB_ICONWARNING : MB_OK);
}

extern "C" __declspec(dllexport) DWORD RequiredVersion() { return 2010900; }
extern "C" __declspec(dllexport) COMMON_PLUGIN_TABLE* GetCommonPluginTable() { return &plugin_table; }
extern "C" __declspec(dllexport) bool InitializePlugin(DWORD) { return true; }
extern "C" __declspec(dllexport) void UninitializePlugin() {}
extern "C" __declspec(dllexport) void RegisterPlugin(HOST_APP_TABLE* host) {
    edit_handle = host->create_edit_handle();
    host->register_edit_menu_param(L"ClipChannel\\字幕を追加", nullptr, import_menu);
}
