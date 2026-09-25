// Included after the shared project-matching and preview helpers.
#include <cstdint>

struct MediaValues {
    std::string asset, kind, identity;
    int rate, rate_scale, video_frames, first, length, preview_frame;
    double offset, volume, x, y, scale;
};
static MediaValues media_values;
static bool media_applied;
static int media_sample_rate;

static bool read_media(const wchar_t* filename) {
    std::ifstream file(std::filesystem::path(filename), std::ios::binary);
    std::string line, video;
    auto field = [&](const char* name, std::string& result) {
        if (!std::getline(file, line) || line.rfind(std::string(name) + "\t", 0) != 0) return false;
        result = line.substr(std::strlen(name) + 1);
        return true;
    };
    auto number = [&](const char* name, double& result) {
        std::string value;
        if (!field(name, value)) return false;
        try {
            size_t used;
            result = std::stod(value, &used);
            return used == value.size() && std::isfinite(result);
        } catch (...) { return false; }
    };
    auto integer = [&](const char* name, int& result) {
        double value;
        if (!number(name, value) || value < 0 || value >= INT_MAX || std::floor(value) != value) return false;
        result = static_cast<int>(value);
        return true;
    };
    MediaValues value{};
    std::string encoded;
    if (!std::getline(file, line) || line != "ClipChannel-Media-1" ||
        !field("video", encoded) || !decode_hex(encoded, video) ||
        !field("asset", encoded) || !decode_hex(encoded, value.asset) ||
        !field("kind", value.kind) || !field("identity", value.identity) ||
        !integer("rate", value.rate) || !integer("rate_scale", value.rate_scale) ||
        !integer("video_frames", value.video_frames) || !integer("first", value.first) ||
        !integer("length", value.length) || !number("offset", value.offset) ||
        !number("volume", value.volume) || !number("x", value.x) || !number("y", value.y) ||
        !number("scale", value.scale) || !integer("preview_frame", value.preview_frame) ||
        std::getline(file, line)) return false;
    if ((value.kind != "image" && value.kind != "bgm" && value.kind != "sound") ||
        value.identity.size() != 32 || value.identity.find_first_not_of("0123456789abcdef") != std::string::npos ||
        value.rate < 1 || value.rate_scale < 1 || value.video_frames < 1 ||
        value.first >= value.video_frames || value.length < 1 || value.length >= INT_MAX - value.first ||
        value.preview_frame >= value.video_frames || value.offset < 0 ||
        value.volume < 0 || value.volume > 1000 || value.scale < 1 || value.scale > 1000 ||
        video.find_first_of("\r\n") != std::string::npos || video.find('\0') != std::string::npos ||
        value.asset.find_first_of("\r\n") != std::string::npos || value.asset.find('\0') != std::string::npos)
        return false;
    auto project_folder = std::filesystem::path(filename).parent_path();
    auto expected = project_folder.parent_path().parent_path() / L"media" / L"supporting" /
                    project_folder.filename() / value.identity;
    std::error_code error;
    auto asset = std::filesystem::u8path(value.asset);
    if (!std::filesystem::is_regular_file(asset, error) ||
        !std::filesystem::equivalent(asset.parent_path(), expected, error)) return false;
    video_path = std::move(video);
    media_values = std::move(value);
    return true;
}

static std::string media_alias() {
    const auto& value = media_values;
    std::string alias = "[Object]\r\nframe=0," + std::to_string(value.length - 1) + "\r\n[Object.0]\r\n";
    if (value.kind == "image") {
        return alias + "effect.name=画像ファイル\r\nファイル=" + value.asset +
            "\r\n表示番号=0\r\n再生速度=100.00\r\nループ再生=0\r\n連番ファイル=0\r\n"
            "[Object.1]\r\neffect.name=標準描画\r\nX=" + decimal(value.x) +
            "\r\nY=" + decimal(value.y) + "\r\nZ=0.00\r\n拡大率=" + decimal(value.scale, 3) +
            "\r\n縦横比=0.000\r\n透明度=0.00\r\n合成モード=通常\r\n";
    }
    double end = value.offset + static_cast<double>(value.length) * value.rate_scale / value.rate;
    return alias + "effect.name=音声ファイル\r\n再生位置=" + decimal(value.offset, 6) + "," +
        decimal(end, 6) + ",再生範囲,0\r\n再生速度=100.00\r\nファイル=" + value.asset +
        "\r\nトラック=0\r\nループ再生=0\r\n[Object.1]\r\neffect.name=音声再生\r\n音量=" +
        decimal(value.volume) + "\r\n左右=0.00\r\n";
}

static void apply_media(EDIT_SECTION* edit) {
    media_applied = false;
    auto video = matching_video(edit);
    const auto& value = media_values;
    if (!video || static_cast<int64_t>(edit->info->rate) * value.rate_scale !=
                  static_cast<int64_t>(value.rate) * edit->info->scale) return;
    auto video_range = edit->get_object_layer_frame(video);
    if (video_range.start != 0 || video_range.end != value.video_frames - 1) return;
    std::wstring name = L"ClipChannel:" + std::wstring(value.identity.begin(), value.identity.end());
    OBJECT_HANDLE previous = nullptr;
    int previous_layer = -1, free_layer = -1;
    bool previous_layer_available = false;
    for (int layer = 0; layer <= (std::max)(edit->info->layer_max + 1, 2); ++layer) {
        bool occupied = false;
        bool has_previous = false;
        int frame = 0;
        while (auto object = edit->find_object(layer, frame)) {
            auto range = edit->get_object_layer_frame(object);
            auto object_name = edit->get_object_name(object);
            if (object_name && name == object_name) {
                // Refuse ambiguous identities rather than deleting a manually duplicated object.
                if (previous) return;
                previous = object;
                previous_layer = layer;
                has_previous = true;
            } else if (range.start < value.first + value.length && range.end >= value.first) {
                occupied = true;
            }
            if (range.end < frame || range.end == INT_MAX) break;
            frame = range.end + 1;
        }
        if (has_previous) previous_layer_available = !occupied;
        if (layer >= 2 && !occupied && !has_previous && free_layer == -1) free_layer = layer;
    }
    if (free_layer < 0) return;
    auto alias = media_alias();
    auto object = edit->create_object_from_alias(alias.c_str(), free_layer, value.first, value.length);
    if (!object) return;
    edit->set_object_name(object, name.c_str());
    if (previous) {
        edit->delete_object(previous);
        if (previous_layer_available && !edit->move_object(object, previous_layer, value.first)) return;
    }
    // Keep the complete audio object, but select only the editing video's output range.
    edit->set_select_range(0, value.video_frames - 1);
    media_sample_rate = edit->info->sample_rate;
    media_applied = true;
}

struct AudioPreview {
    std::ofstream output;
    uint32_t samples = 0;
    bool received = false;
};

static void write_audio_preview(void* parameter, int, const float* left, const float* right, int count) {
    auto& audio = *static_cast<AudioPreview*>(parameter);
    if (!left || !right || count < 1) return;
    for (int i = 0; i < count; ++i) {
        audio.output.write(reinterpret_cast<const char*>(left + i), sizeof(float));
        audio.output.write(reinterpret_cast<const char*>(right + i), sizeof(float));
    }
    audio.samples += count;
    audio.received = true;
}

static bool render_media_preview() {
    auto picture = selected_file;
    picture.replace_extension(L".ppm");
    auto sound = selected_file;
    sound.replace_extension(L".wav");
    std::error_code ignored;
    std::filesystem::remove(picture, ignored);
    std::filesystem::remove(sound, ignored);
    if (!edit_handle->rendering_scene_video(media_values.preview_frame, nullptr, write_preview)) return false;
    edit_handle->wait_rendering_task();
    if (!std::filesystem::is_regular_file(picture) || media_sample_rate < 1) return false;
    AudioPreview audio{std::ofstream(sound, std::ios::binary | std::ios::trunc)};
    if (!audio.output) return false;
    audio.output.write("RIFF\0\0\0\0WAVEfmt ", 16);
    auto u32 = [&](uint32_t value) { audio.output.write(reinterpret_cast<const char*>(&value), 4); };
    auto u16 = [&](uint16_t value) { audio.output.write(reinterpret_cast<const char*>(&value), 2); };
    u32(16); u16(3); u16(2); u32(media_sample_rate); u32(media_sample_rate * 8);
    u16(8); u16(32); audio.output.write("data", 4); u32(0);
    const int count = static_cast<int>(std::min<int64_t>(media_values.video_frames - media_values.preview_frame,
        (static_cast<int64_t>(media_values.rate) * 5 + media_values.rate_scale - 1) / media_values.rate_scale));
    bool complete = true;
    for (int index = 0; index < count; ++index) {
        audio.received = false;
        if (!edit_handle->rendering_scene_audio(media_values.preview_frame + index, &audio, write_audio_preview)) {
            complete = false;
            break;
        }
        edit_handle->wait_rendering_task();
        if (!audio.received || !audio.output) { complete = false; break; }
    }
    audio.output.seekp(4); u32(36 + audio.samples * 8);
    audio.output.seekp(40); u32(audio.samples * 8);
    audio.output.flush();
    complete = complete && static_cast<bool>(audio.output);
    audio.output.close();
    if (!complete) std::filesystem::remove(sound, ignored);
    return complete;
}

static int apply_media_file(const wchar_t* filename) {
    media_applied = false;
    if (!read_media(filename)) return 0;
    selected_file = std::filesystem::path(filename);
    if (!edit_handle->call_edit_section(apply_media) || !media_applied) return 0;
    return render_media_preview() ? 1 : 2;
}
