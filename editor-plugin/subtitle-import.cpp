// AviUtl2 plugin: append editable text objects from a ClipChannel subtitle file.
#include <windows.h>
#include <commdlg.h>
#include <algorithm>
#include <array>
#include <climits>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <set>
#include <string>
#include <tuple>
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
static std::array<double, 13> layout_values;
static bool layout_applied;

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

static bool read_layout(const wchar_t* path) {
    std::ifstream file(std::filesystem::path(path), std::ios::binary);
    std::string line, encoded;
    if (!std::getline(file, line) || line != "ClipChannel-Layout-1") return false;
    if (!std::getline(file, line) || line.rfind("video\t", 0) != 0 ||
        !decode_hex(line.substr(6), encoded)) return false;
    constexpr const char* names[] = {"width", "height", "scale", "x", "y",
        "crop_left", "crop_top", "crop_right", "crop_bottom", "subtitle_x",
        "subtitle_y", "subtitle_size", "preview_frame"};
    std::array<double, 13> values{};
    for (size_t index = 0; index < values.size(); ++index) {
        if (!std::getline(file, line) || line.rfind(std::string(names[index]) + "\t", 0) != 0)
            return false;
        try {
            size_t used = 0;
            values[index] = std::stod(line.substr(std::strlen(names[index]) + 1), &used);
            if (used != line.size() - std::strlen(names[index]) - 1 || !std::isfinite(values[index]))
                return false;
        } catch (...) { return false; }
    }
    if (std::getline(file, line) || values[0] < 1 || values[0] > 8192 ||
        values[1] < 1 || values[1] > 8192 || values[2] < 1 || values[2] > 1000 ||
        values[11] < 1 || values[11] > 300 || values[12] < 0 ||
        values[12] > INT_MAX || std::floor(values[12]) != values[12]) return false;
    for (int index = 5; index <= 8; ++index) if (values[index] < 0) return false;
    video_path = std::move(encoded);
    layout_values = values;
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

static std::string alias_for(const std::string& text, int length) {
    std::string escaped;
    for (size_t i = 0; i < text.size(); ++i) {
        if (text[i] == '\r') {
            if (i + 1 < text.size() && text[i + 1] == '\n') ++i;
            escaped += "\\n";
        } else if (text[i] == '\n') escaped += "\\n";
        else escaped += text[i];
    }
    return "[Object]\r\nframe=0," + std::to_string(length - 1) +
           "\r\n[Object.0]\r\neffect.name=テキスト\r\n"
           "サイズ=40.00\r\n字間=0.00\r\n行間=0.00\r\n表示速度=0.00\r\n"
           "フォント=Yu Gothic UI\r\n文字色=ffffff\r\n影・縁色=000000\r\n"
           "文字装飾=標準文字\r\n文字揃え=中央揃え[下]\r\nB=0\r\nI=0\r\n"
           "テキスト=" + escaped + "\r\n文字毎に個別オブジェクト=0\r\n"
           "自動スクロール=0\r\n移動座標上に表示=0\r\n"
           "オブジェクトの長さを自動調節=0\r\n[Object.1]\r\n"
           "effect.name=標準描画\r\nX=0.00\r\nY=350.00\r\nZ=0.00\r\n"
           "拡大率=100.000\r\n縦横比=0.000\r\n透明度=0.00\r\n合成モード=通常\r\n";
}

static OBJECT_HANDLE matching_video(EDIT_SECTION* edit) {
    auto project = edit->get_project_file(edit_handle);
    auto path = project ? project->get_project_file_path() : nullptr;
    if (!path || std::filesystem::path(path).parent_path() != selected_file.parent_path())
        return nullptr;
    std::string normalized = video_path;
    std::replace(normalized.begin(), normalized.end(), '\\', '/');
    for (int layer = 0; layer < 32; ++layer) {
        auto object = edit->find_object(layer, 0);
        auto alias = object ? edit->get_object_alias(object) : nullptr;
        if (alias && std::string(alias).find("ファイル=" + normalized + "\r\n") != std::string::npos)
            return object;
    }
    return nullptr;
}

static std::string decimal(double value, int precision = 2) {
    std::ostringstream stream;
    stream.setf(std::ios::fixed);
    stream.precision(precision);
    stream << value;
    return stream.str();
}

static void apply_layout(EDIT_SECTION* edit) {
    layout_applied = false;
    auto video = matching_video(edit);
    if (!video) return;
    auto set_video = [&](const wchar_t* item, double value, int precision = 2) {
        return edit->set_object_item_value(video, L"映像再生", item, decimal(value, precision).c_str());
    };
    if (!set_video(L"X", layout_values[3]) || !set_video(L"Y", layout_values[4]) ||
        !set_video(L"拡大率", layout_values[2], 3)) return;
    const bool crop_requested = layout_values[5] || layout_values[6] || layout_values[7] || layout_values[8];
    if (crop_requested && !edit->find_effect(video, L"クリッピング") &&
        !edit->create_effect(video, L"クリッピング")) return;
    if (edit->find_effect(video, L"クリッピング")) {
        constexpr const wchar_t* sides[] = {L"左", L"上", L"右", L"下"};
        for (int index = 0; index < 4; ++index)
            if (!edit->set_object_item_value(video, L"クリッピング", sides[index],
                    decimal(layout_values[index + 5], 0).c_str())) return;
    }
    // Match only captions represented by this editing video's saved import files.
    std::set<std::tuple<int, int, std::string>> imported_captions;
    const auto layout_video = video_path;
    for (const auto& entry : std::filesystem::directory_iterator(selected_file.parent_path())) {
        if (entry.path().extension() != L".ccsub" || !read_captions(entry.path().c_str()) ||
            video_path != layout_video) continue;
        for (const auto& caption : captions) {
            auto alias = alias_for(caption.text, caption.last - caption.first + 1);
            auto start = alias.find("テキスト=");
            auto end = alias.find("\r\n", start);
            imported_captions.emplace(caption.first, caption.last, alias.substr(start, end - start));
        }
    }
    video_path = layout_video;
    for (int layer = 2; layer < 512; ++layer) {
        int frame = 0;
        while (auto object = edit->find_object(layer, frame)) {
            auto range = edit->get_object_layer_frame(object);
            auto alias = edit->get_object_alias(object);
            bool is_imported = false;
            for (const auto& item : imported_captions) {
                if (std::get<0>(item) == range.start && std::get<1>(item) == range.end &&
                    alias && std::string(alias).find(std::get<2>(item) + "\r\n") != std::string::npos) {
                    is_imported = true;
                    break;
                }
            }
            if (is_imported) {
                if (!edit->set_object_item_value(object, L"標準描画", L"X",
                        decimal(layout_values[9]).c_str()) ||
                    !edit->set_object_item_value(object, L"標準描画", L"Y",
                        decimal(layout_values[10]).c_str()) ||
                    !edit->set_object_item_value(object, L"テキスト", L"サイズ",
                        decimal(layout_values[11], 2).c_str())) return;
            }
            if (range.end < frame || range.end == INT_MAX) break;
            frame = range.end + 1;
        }
    }
    edit->set_scene_size(static_cast<int>(layout_values[0]), static_cast<int>(layout_values[1]));
    layout_applied = true;
}

static void write_preview(void*, int, const void* buffer, int width, int height, int pitch) {
    if (!buffer || width < 1 || height < 1 || pitch < width * 4) return;
    auto path = selected_file;
    path.replace_extension(L".ppm");
    std::ofstream output(path, std::ios::binary | std::ios::trunc);
    if (!output) return;
    output << "P6\n" << width << " " << height << "\n255\n";
    auto bytes = static_cast<const unsigned char*>(buffer);
    for (int y = 0; y < height; ++y) {
        auto row = bytes + static_cast<size_t>(y) * pitch;
        for (int x = 0; x < width; ++x)
            output.write(reinterpret_cast<const char*>(row + static_cast<size_t>(x) * 4), 3);
    }
}

static void create_objects(EDIT_SECTION* edit) {
    imported = rejected = 0;
    matching_project = matching_video(edit) != nullptr;
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
        auto alias = alias_for(row.text, row.last - row.first + 1);
        if (edit->create_object_from_alias(alias.c_str(), layer, row.first, row.last - row.first + 1))
            ++imported;
        else ++rejected;
    }
}

static void layout_menu(void*) {
    wchar_t filename[32768] = L"";
    OPENFILENAMEW dialog{};
    dialog.lStructSize = sizeof(dialog);
    dialog.hwndOwner = GetActiveWindow();
    dialog.lpstrFilter = L"ClipChannel layout (*.cclayout)\0*.cclayout\0\0";
    dialog.lpstrFile = filename;
    dialog.nMaxFile = 32768;
    dialog.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST;
    if (!GetOpenFileNameW(&dialog)) return;
    if (!read_layout(filename)) {
        MessageBoxW(nullptr, L"画面設定ファイルを読み取れません", L"ClipChannel", MB_ICONERROR);
        return;
    }
    selected_file = std::filesystem::path(filename);
    layout_applied = false;
    if (!edit_handle->call_edit_section(apply_layout) || !layout_applied) {
        MessageBoxW(nullptr, L"画面設定を適用できません。対応する編集フォルダ・動画と各効果を確認してください", L"ClipChannel", MB_ICONERROR);
        return;
    }
    auto preview = selected_file;
    preview.replace_extension(L".ppm");
    std::error_code ignored;
    std::filesystem::remove(preview, ignored);
    bool requested = edit_handle->rendering_scene_video(static_cast<int>(layout_values[12]), nullptr, write_preview);
    if (requested) edit_handle->wait_rendering_task();
    MessageBoxW(nullptr, requested && std::filesystem::is_regular_file(preview)
        ? L"画面設定を適用しました。アプリでプレビューを開いて確認してください"
        : L"画面設定は適用されましたが、プレビューを生成できませんでした",
        L"ClipChannel", requested && std::filesystem::is_regular_file(preview) ? MB_OK : MB_ICONWARNING);
}

static void import_menu(void*) {
    wchar_t filename[32768] = L"";
    OPENFILENAMEW dialog{};
    dialog.lStructSize = sizeof(dialog);
    dialog.hwndOwner = GetActiveWindow();
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
    host->register_edit_menu_param(L"ClipChannel\\画面設定を適用", nullptr, layout_menu);
}
