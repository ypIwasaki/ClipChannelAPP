// Save the live host project and render its scene through AviUtl2 before encoding.
// The SDK does not expose a save command; resolve the host's labelled menu at runtime.
#include <atomic>
#include <dlgs.h>
#include <iomanip>
#include <map>
#include <memory>
#include <thread>

static constexpr UINT control_finished_message = WM_APP + 114;
static std::atomic<bool> export_busy{false};
static std::atomic<bool> export_cancel{false};
static std::thread export_thread;
static std::filesystem::path control_project_path;
static std::atomic<uint64_t> control_revision{0};
static std::vector<HWND> disabled_host_windows;

struct ControlRequest {
    std::filesystem::path instruction, project, output, ffmpeg;
    std::string action, video;
    int width = 0, height = 0, rate = 0, scale = 0, bitrate = 0, audio_rate = 0;
};
struct ControlSnapshot {
    bool matched = false, dirty = true;
    int width = 0, height = 0, rate = 0, scale = 0, sample_rate = 0, frames = 0;
    std::string fingerprint;
};
struct ControlJob {
    ControlRequest request;
    ControlSnapshot snapshot;
    std::atomic<int> rendered{0};
    std::string terminal = "failed", detail;
};
static std::unique_ptr<ControlJob> active_export;
static std::unique_ptr<ControlRequest> initial_save_request;
static ControlSnapshot initial_save_snapshot;
static ULONGLONG initial_save_deadline = 0;

static std::filesystem::path control_sidecar(const std::filesystem::path& path, const wchar_t* suffix) {
    auto result = path;
    result.replace_extension(suffix);
    return result;
}
static std::wstring control_wide(const std::string& value) {
    if (value.empty()) return {};
    int length = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, value.data(), static_cast<int>(value.size()), nullptr, 0);
    if (!length) return {};
    std::wstring result(length, L'\0');
    MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, value.data(), static_cast<int>(value.size()), result.data(), length);
    return result;
}
static std::string control_json(const std::string& value) {
    std::string result = "\"";
    for (unsigned char c : value) {
        if (c == '\\' || c == '"') { result += '\\'; result += c; }
        else if (c == '\n') result += "\\n";
        else if (c == '\r') result += "\\r";
        else if (c < 32) result += '?';
        else result += c;
    }
    return result + '"';
}
static bool control_response(const ControlRequest& request, const ControlSnapshot& info,
                             const std::string& state, const std::string& detail = "", double progress = 0) {
    auto path = control_sidecar(request.instruction, L".json");
    auto temporary = path;
    temporary += L".tmp";
    std::ofstream output(temporary, std::ios::binary | std::ios::trunc);
    output << "{\"state\":" << control_json(state) << ",\"detail\":" << control_json(detail)
        << ",\"process_id\":" << GetCurrentProcessId() << ",\"dirty\":" << (info.dirty ? "true" : "false")
        << ",\"busy\":" << (export_busy ? "true" : "false")
        << ",\"fingerprint\":" << control_json(info.fingerprint)
        << ",\"width\":" << info.width << ",\"height\":" << info.height
        << ",\"rate\":" << info.rate << ",\"scale\":" << info.scale
        << ",\"frames\":" << info.frames << ",\"progress\":" << progress << "}\n";
    output.flush();
    bool okay = static_cast<bool>(output);
    output.close();
    return okay && MoveFileExW(temporary.c_str(), path.c_str(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH);
}
static bool read_control(const wchar_t* filename, ControlRequest& request) {
    request.instruction = filename;
    std::ifstream input(request.instruction, std::ios::binary);
    std::string line;
    if (!std::getline(input, line)) return false;
    if (!line.empty() && line.back() == '\r') line.pop_back();
    if (line != "ClipChannel-Control-1") return false;
    std::map<std::string, std::string> fields;
    while (std::getline(input, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        auto tab = line.find('\t');
        if (tab == std::string::npos || !fields.emplace(line.substr(0, tab), line.substr(tab + 1)).second) return false;
    }
    if (!input.eof() || !fields.count("action") || !fields.count("project") || !fields.count("video")) return false;
    request.action = fields["action"];
    if (request.action != "status" && request.action != "save" && request.action != "export") return false;
    std::string project;
    if (!decode_hex(fields["project"], project) || !decode_hex(fields["video"], request.video) ||
        project.find('\0') != std::string::npos || request.video.find('\0') != std::string::npos) return false;
    request.project = control_wide(project);
    if (!request.project.is_absolute() || request.project.parent_path() != request.instruction.parent_path()) return false;
    if (request.action != "export") return fields.size() == 3;
    if (fields.size() != 11) return false;
    auto parse_path = [&](const char* name, std::filesystem::path& path) {
        std::string value;
        if (!fields.count(name) || !decode_hex(fields[name], value) || value.find('\0') != std::string::npos) return false;
        path = control_wide(value);
        return path.is_absolute();
    };
    auto parse_int = [&](const char* name, int& value) {
        if (!fields.count(name)) return false;
        try { size_t end; value = std::stoi(fields[name], &end); return end == fields[name].size(); }
        catch (...) { return false; }
    };
    if (!parse_path("output", request.output) || !parse_path("ffmpeg", request.ffmpeg) ||
        !parse_int("width", request.width) || !parse_int("height", request.height) ||
        !parse_int("rate", request.rate) || !parse_int("scale", request.scale) ||
        !parse_int("bitrate", request.bitrate) || !parse_int("audio_rate", request.audio_rate)) return false;
    auto extension = request.output.extension().wstring();
    std::transform(extension.begin(), extension.end(), extension.begin(), [](wchar_t value) { return static_cast<wchar_t>(towlower(value)); });
    return request.width >= 2 && request.width <= 8192 && !(request.width % 2) &&
        request.height >= 2 && request.height <= 8192 && !(request.height % 2) &&
        request.rate > 0 && request.scale > 0 && static_cast<double>(request.rate) / request.scale <= 240 &&
        request.bitrate >= 100000 && request.bitrate <= 500000000 &&
        request.audio_rate >= 8000 && request.audio_rate <= 192000 &&
        extension == L".mp4" && !std::filesystem::exists(request.output) &&
        std::filesystem::is_regular_file(request.ffmpeg);
}

static void control_snapshot(EDIT_SECTION* edit, ControlSnapshot& result,
                             const std::filesystem::path* target = nullptr, const std::string* video = nullptr) {
    const wchar_t* path = control_project_path.empty() ? nullptr : control_project_path.c_str();
    if (path && *path && target && std::filesystem::path(path) != *target) return;
    EDIT_INFO info{};
    edit_handle->get_edit_info(&info, sizeof(info));
    result.width = info.width; result.height = info.height;
    result.rate = info.rate; result.scale = info.scale; result.sample_rate = info.sample_rate;
    std::ostringstream content;
    content << GetCurrentProcessId() << ',' << control_revision.load() << ',';
    content << info.scene_id << ',' << info.width << ',' << info.height << ',' << info.rate << ',' << info.scale << ',' << info.sample_rate << '\n';
    bool found_video = video == nullptr;
    std::string normalized = video ? *video : "";
    std::replace(normalized.begin(), normalized.end(), '\\', '/');
    for (int layer = 0; layer <= info.layer_max; ++layer) {
        content << layer << ':' << edit->get_layer_enable(layer) << ',' << edit->get_layer_lock(layer) << '\n';
        auto layer_name = edit->get_layer_name(layer);
        if (layer_name) content.write(reinterpret_cast<const char*>(layer_name), wcslen(layer_name) * sizeof(wchar_t));
        int frame = 0;
        while (auto object = edit->find_object(layer, frame)) {
            auto range = edit->get_object_layer_frame(object);
            auto alias = edit->get_object_alias(object);
            if (!alias) return;
            std::string data(alias);
            auto object_name = edit->get_object_name(object);
            if (object_name) content.write(reinterpret_cast<const char*>(object_name), wcslen(object_name) * sizeof(wchar_t));
            content << layer << ',' << range.start << ',' << range.end << ':' << data.size() << ':' << data;
            if (data.find("effect.name=動画ファイル\r\n") != std::string::npos) {
                if (range.end == INT_MAX) return;
                result.frames = (std::max)(result.frames, range.end + 1);
                if (video && (data.find("ファイル=" + *video + "\r\n") != std::string::npos ||
                              data.find("ファイル=" + normalized + "\r\n") != std::string::npos)) found_video = true;
            }
            if (range.end < frame || range.end == INT_MAX) break;
            frame = range.end + 1;
        }
    }
    // A stable digest of live aliases includes manual changes as well as app edits.
    uint64_t digest = 14695981039346656037ULL;
    for (unsigned char value : content.str()) { digest ^= value; digest *= 1099511628211ULL; }
    std::ostringstream hash;
    hash << std::hex << std::setfill('0') << std::setw(16) << digest;
    result.fingerprint = hash.str();
    result.matched = found_video && result.frames > 0 && info.rate > 0 && info.scale > 0 && info.sample_rate > 0;
    if (!path || !*path) return;
    std::ifstream saved(std::filesystem::path(path), std::ios::binary);
    std::string line;
    while (std::getline(saved, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line == "clipchannel.saved_fingerprint=" + result.fingerprint) result.dirty = false;
    }
}
static void load_control_project(PROJECT_FILE* project) {
    auto path = project->get_project_file_path();
    control_project_path = path ? path : L"";
}
static void control_changed(void*) { ++control_revision; }
static void save_control_marker(PROJECT_FILE* project) {
    load_control_project(project);
    ControlSnapshot snapshot;
    edit_handle->call_read_section_param(&snapshot, [](void* data, EDIT_SECTION* edit) {
        control_snapshot(edit, *static_cast<ControlSnapshot*>(data));
    });
    if (!snapshot.fingerprint.empty()) project->set_param_string("clipchannel.saved_fingerprint", snapshot.fingerprint.c_str());
}
static UINT find_save_menu(HMENU menu) {
    UINT found = 0;
    for (int index = 0; index < GetMenuItemCount(menu); ++index) {
        wchar_t title[512]{};
        MENUITEMINFOW item{};
        item.cbSize = sizeof(item);
        item.fMask = MIIM_STRING | MIIM_ID | MIIM_SUBMENU | MIIM_STATE;
        item.dwTypeData = title; item.cch = 511;
        if (!GetMenuItemInfoW(menu, index, TRUE, &item)) continue;
        std::wstring name(title);
        name = name.substr(0, name.find(L'\t'));
        name.erase(std::remove(name.begin(), name.end(), L'&'), name.end());
        if (name == L"プロジェクトを保存" || name == L"プロジェクトの保存" || name == L"上書き保存") {
            if (item.fState & (MFS_DISABLED | MFS_GRAYED)) continue;
            if (found) return 0;
            found = item.wID;
        }
        if (item.hSubMenu) {
            UINT nested = find_save_menu(item.hSubMenu);
            if (found && nested) return 0;
            if (nested) found = nested;
        }
    }
    return found;
}
static void unlock_export_windows() {
    for (HWND window : disabled_host_windows) if (IsWindow(window)) EnableWindow(window, TRUE);
    disabled_host_windows.clear();
}
static BOOL CALLBACK lock_export_window(HWND window, LPARAM) {
    DWORD process = 0;
    GetWindowThreadProcessId(window, &process);
    if (process == GetCurrentProcessId() && IsWindowEnabled(window)) {
        disabled_host_windows.push_back(window);
        EnableWindow(window, FALSE);
    }
    return TRUE;
}
struct ControlHandle {
    HANDLE value = INVALID_HANDLE_VALUE;
    ~ControlHandle() { close(); }
    void close() { if (value != INVALID_HANDLE_VALUE && value != nullptr) CloseHandle(value); value = INVALID_HANDLE_VALUE; }
};
static std::wstring quote_argument(const std::wstring& value) {
    std::wstring result = L"\"";
    unsigned slashes = 0;
    for (wchar_t c : value) {
        if (c == L'\\') { ++slashes; continue; }
        if (c == L'"') result.append(slashes * 2 + 1, L'\\');
        else result.append(slashes, L'\\');
        slashes = 0;
        result += c;
    }
    result.append(slashes * 2, L'\\');
    return result + L'"';
}
static bool export_cancelled(const ControlJob& job) {
    std::error_code error;
    return export_cancel || std::filesystem::exists(control_sidecar(job.request.instruction, L".cancel"), error);
}
struct ExportVideoFrame {
    HANDLE pipe;
    int width, height;
    bool received = false;
};
static void stream_export_video(void* parameter, int, const void* buffer, int width, int height, int pitch) {
    auto& frame = *static_cast<ExportVideoFrame*>(parameter);
    if (!buffer || width != frame.width || height != frame.height || pitch < width * 4) return;
    for (int y = 0; y < height; ++y) {
        auto row = static_cast<const unsigned char*>(buffer) + static_cast<size_t>(y) * pitch;
        DWORD remaining = static_cast<DWORD>(width * 4);
        while (remaining) {
            DWORD written = 0;
            if (!WriteFile(frame.pipe, row, remaining, &written, nullptr) || !written) return;
            row += written; remaining -= written;
        }
    }
    frame.received = true;
}
static void run_export(ControlJob& job) {
    const auto& request = job.request;
    const auto& info = job.snapshot;
    auto audio_path = control_sidecar(request.instruction, L".f32le");
    auto error_path = control_sidecar(request.instruction, L".log");
    ControlHandle read_pipe, write_pipe, process, log;
    auto cancelled = [&]() { return export_cancelled(job); };
    try {
        AudioPreview audio{std::ofstream(audio_path, std::ios::binary | std::ios::trunc)};
        if (!audio.output) throw std::runtime_error("audio-temporary-file-unavailable");
        for (int frame = 0; frame < info.frames; ++frame) {
            if (cancelled()) break;
            audio.received = false;
            if (!edit_handle->rendering_scene_audio(frame, &audio, write_audio_preview)) throw std::runtime_error("host-audio-render-rejected");
            edit_handle->wait_rendering_task();
            if (!audio.received || !audio.output) throw std::runtime_error("host-audio-render-incomplete");
            if (frame % 15 == 0) control_response(request, info, "running", "audio", 0.25 * frame / info.frames);
        }
        audio.output.close();
        if (cancelled()) job.terminal = "cancelled";
        else {
            SECURITY_ATTRIBUTES security{sizeof(security), nullptr, TRUE};
            if (!CreatePipe(&read_pipe.value, &write_pipe.value, &security, 0) ||
                !SetHandleInformation(write_pipe.value, HANDLE_FLAG_INHERIT, 0)) throw std::runtime_error("encoder-pipe-unavailable");
            log.value = CreateFileW(error_path.c_str(), GENERIC_WRITE, FILE_SHARE_READ, &security, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
            if (log.value == INVALID_HANDLE_VALUE) throw std::runtime_error("encoder-log-unavailable");

            const auto output_frames = static_cast<int64_t>(std::ceil(static_cast<long double>(info.frames) * info.scale * request.rate / info.rate / request.scale));
            std::wstring filter = L"scale=" + std::to_wstring(request.width) + L":" + std::to_wstring(request.height) +
                L":flags=lanczos:out_color_matrix=bt709,tpad=stop_mode=clone:stop_duration=1,fps=" + std::to_wstring(request.rate) + L"/" + std::to_wstring(request.scale);
            std::wstring command = quote_argument(request.ffmpeg.wstring()) + L" -hide_banner -loglevel error -nostdin -n -f rawvideo -pixel_format rgba -video_size " +
                std::to_wstring(info.width) + L"x" + std::to_wstring(info.height) + L" -framerate " + std::to_wstring(info.rate) + L"/" + std::to_wstring(info.scale) +
                L" -i pipe:0 -f f32le -ar " + std::to_wstring(info.sample_rate) + L" -ac 2 -i " + quote_argument(audio_path.wstring()) +
                L" -map 0:v:0 -map 1:a:0 -vf " + quote_argument(filter) + L" -frames:v " + std::to_wstring(output_frames) +
                L" -t " + control_wide(decimal(static_cast<double>(output_frames) * request.scale / request.rate, 9)) + L" -c:v libx264 -preset medium -b:v " + std::to_wstring(request.bitrate) +
                L" -pix_fmt yuv420p -x264-params colorprim=bt709:transfer=bt709:colormatrix=bt709 -color_range tv -colorspace bt709 -color_primaries bt709 -color_trc bt709 -c:a aac -profile:a aac_low -b:a 192k -ar " +
                std::to_wstring(request.audio_rate) + L" -movflags +faststart " + quote_argument(request.output.wstring());
            STARTUPINFOW startup{};
            startup.cb = sizeof(startup); startup.dwFlags = STARTF_USESTDHANDLES;
            startup.hStdInput = read_pipe.value; startup.hStdOutput = log.value; startup.hStdError = log.value;
            PROCESS_INFORMATION child{};
            if (!CreateProcessW(request.ffmpeg.c_str(), command.data(), nullptr, nullptr, TRUE, CREATE_NO_WINDOW, nullptr, nullptr, &startup, &child))
                throw std::runtime_error("encoder-start-failed");
            process.value = child.hProcess; CloseHandle(child.hThread); read_pipe.close();
            for (int frame = 0; frame < info.frames; ++frame) {
                if (cancelled()) break;
                ExportVideoFrame image{write_pipe.value, info.width, info.height};
                if (!edit_handle->rendering_scene_video(frame, &image, stream_export_video)) throw std::runtime_error("host-video-render-rejected");
                edit_handle->wait_rendering_task();
                if (!image.received) throw std::runtime_error("host-video-render-incomplete");
                job.rendered = frame + 1;
                if (frame % 10 == 0) control_response(request, info, "running", "video", 0.25 + 0.70 * (frame + 1) / info.frames);
            }
            write_pipe.close();
            // EOF lets FFmpeg finish its current frame and close cleanly on normal cancellation.
            WaitForSingleObject(process.value, INFINITE);
            DWORD exit_code = 1;
            GetExitCodeProcess(process.value, &exit_code);
            if (cancelled()) job.terminal = "cancelled";
            else if (exit_code || job.rendered != info.frames) throw std::runtime_error("encoder-output-incomplete-see-log");
            else job.terminal = "completed";
        }
    } catch (const std::exception& error) { job.detail = error.what(); }
    catch (...) { job.detail = "unexpected-export-error"; }
    write_pipe.close();
    if (process.value != INVALID_HANDLE_VALUE) WaitForSingleObject(process.value, INFINITE);
    std::error_code ignored;
    std::filesystem::remove(audio_path, ignored);
    // Partial outputs remain inspectable; the app never calls them completed.
    PostMessageW(layout_bridge_window, control_finished_message, 0, 0);
}
static bool finish_control_export() {
    if (!active_export) return false;
    if (export_thread.joinable()) export_thread.join();
    unlock_export_windows();
    export_busy = false;
    control_response(active_export->request, active_export->snapshot, active_export->terminal,
                     active_export->detail, active_export->terminal == "completed" ? 1 : 0);
    active_export.reset();
    return true;
}
static int apply_control_file(const wchar_t* filename) {
    ControlRequest request;
    if (!read_control(filename, request)) return 0;
    if (export_busy) {
        if (!active_export || request.project != active_export->request.project) return 0;
        control_response(request, active_export->snapshot, request.action == "status" ? "running" : "failed", "editing-is-blocked-until-export-stops",
                         static_cast<double>(active_export->rendered) / active_export->snapshot.frames);
        return request.action == "status" ? 1 : 2;
    }
    ControlSnapshot snapshot;
    struct State { ControlRequest* request; ControlSnapshot* snapshot; } state{&request, &snapshot};
    bool read = edit_handle->call_read_section_param(&state, [](void* parameter, EDIT_SECTION* edit) {
        auto& data = *static_cast<State*>(parameter);
        control_snapshot(edit, *data.snapshot, &data.request->project, &data.request->video);
    });
    if (!read || !snapshot.matched) return 0;
    if (request.action == "status") return control_response(request, snapshot, "ready") ? 1 : 0;
    if (edit_handle->get_edit_state() != EDIT_HANDLE::EDIT_STATE_EDIT) {
        control_response(request, snapshot, "failed", "host-is-not-editable"); return 1;
    }
    if (request.action == "save") {
        HWND host = edit_handle->get_host_app_window();
        UINT command = find_save_menu(GetMenu(host));
        if (!command) { control_response(request, snapshot, "failed", "save-menu-not-identified"); return 1; }
        if (control_project_path.empty()) {
            if (std::filesystem::exists(request.project)) {
                control_response(request, snapshot, "failed", "initial-save-target-already-exists"); return 1;
            }
            initial_save_request = std::make_unique<ControlRequest>(request);
            initial_save_snapshot = snapshot;
            initial_save_deadline = GetTickCount64() + 8000;
            SetTimer(layout_bridge_window, 14, 100, nullptr);
            PostMessageW(host, WM_COMMAND, command, 0);
        } else SendMessageW(host, WM_COMMAND, command, 0);
        return control_response(request, snapshot, "requested", "verify-project-file-before-export") ? 1 : 0;
    }
    if (snapshot.dirty) { control_response(request, snapshot, "failed", "save-project-before-export"); return 1; }
    export_cancel = false;
    export_busy = true;
    EnumWindows(lock_export_window, 0);
    active_export = std::make_unique<ControlJob>();
    active_export->request = request; active_export->snapshot = snapshot;
    control_response(request, snapshot, "running", "audio");
    try { export_thread = std::thread([] { run_export(*active_export); }); }
    catch (...) {
        unlock_export_windows(); export_busy = false; active_export.reset();
        control_response(request, snapshot, "failed", "export-worker-unavailable");
    }
    return 1;
}
struct InitialFilenameField { HWND window = nullptr; int matches = 0; };
static BOOL CALLBACK find_initial_filename_field(HWND window, LPARAM parameter) {
    auto& field = *reinterpret_cast<InitialFilenameField*>(parameter);
    wchar_t name[64]{}, parent_name[64]{};
    GetClassNameW(window, name, 64);
    GetClassNameW(GetParent(window), parent_name, 64);
    // Windows 11's observed common Save As dialog exposes its filename as this
    // Edit child; the address bar has a different control ID. Refuse ambiguity.
    if (GetDlgCtrlID(window) == 1001 && std::wstring(name) == L"Edit" &&
        std::wstring(parent_name) == L"ComboBox") {
        field.window = window;
        ++field.matches;
    }
    return TRUE;
}
static BOOL CALLBACK submit_initial_save_dialog(HWND dialog, LPARAM parameter) {
    auto& submitted = *reinterpret_cast<bool*>(parameter);
    DWORD process = 0;
    GetWindowThreadProcessId(dialog, &process);
    if (process != GetCurrentProcessId() || !IsWindowVisible(dialog)) return TRUE;
    wchar_t class_name[64]{}, title[512]{};
    GetClassNameW(dialog, class_name, 64);
    GetWindowTextW(dialog, title, 512);
    if (std::wstring(class_name) != L"#32770" || std::wstring(title).find(L"保存") == std::wstring::npos) return TRUE;
    HWND owner = GetWindow(dialog, GW_OWNER);
    const HWND host = edit_handle->get_host_app_window();
    while (owner && owner != host) owner = GetWindow(owner, GW_OWNER);
    if (owner != host || !GetDlgItem(dialog, IDOK)) return TRUE;
    if (GetDlgItem(dialog, edt1) || GetDlgItem(dialog, cmb13)) {
        // Legacy Explorer-style common dialogs expose the documented CDM API.
        SendMessageW(dialog, CDM_SETCONTROLTEXT, edt1, reinterpret_cast<LPARAM>(initial_save_request->project.c_str()));
    } else {
        InitialFilenameField field;
        EnumChildWindows(dialog, find_initial_filename_field, reinterpret_cast<LPARAM>(&field));
        if (field.matches != 1 || !SetWindowTextW(field.window, initial_save_request->project.c_str())) return TRUE;
        std::vector<wchar_t> observed(initial_save_request->project.wstring().size() + 2);
        GetWindowTextW(field.window, observed.data(), static_cast<int>(observed.size()));
        if (initial_save_request->project.wstring() != observed.data()) return TRUE;
    }
    PostMessageW(dialog, WM_COMMAND, MAKEWPARAM(IDOK, BN_CLICKED), reinterpret_cast<LPARAM>(GetDlgItem(dialog, IDOK)));
    submitted = true;
    return FALSE;
}
static void poll_initial_save() {
    if (!initial_save_request) { KillTimer(layout_bridge_window, 14); return; }
    bool submitted = false;
    EnumWindows(submit_initial_save_dialog, reinterpret_cast<LPARAM>(&submitted));
    if (submitted || GetTickCount64() >= initial_save_deadline) {
        KillTimer(layout_bridge_window, 14);
        if (!submitted) control_response(*initial_save_request, initial_save_snapshot, "failed", "initial-save-dialog-not-identified");
        initial_save_request.reset();
    }
}
static void shutdown_control() {
    export_cancel = true;
    if (export_thread.joinable()) export_thread.join();
    unlock_export_windows();
}
