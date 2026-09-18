// THROWAWAY validation observer, not a product integration plugin.
// v2: explicit menu changes two fixture captions in one SDK edit section. No automatic commands.
#include <windows.h>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <string>
#include "plugin2.h"
static HMODULE module_handle;
static std::filesystem::path log_path;
static std::mutex log_mutex;
static EDIT_HANDLE* edit_handle;
static unsigned long long save_sequence=0;
static std::string session;
static COMMON_PLUGIN_TABLE table={L"ClipChannel SDK Edit Probe",L"Throwaway SDK edit probe v2 - fixture only"};
static std::string escape(const char* text) {
 std::string out;
 if(!text) return out;
 for(auto p=(const unsigned char*)text;*p;++p) {
  if(*p=='"'||*p=='\\') {out+='\\';out+=char(*p);}
  else if(*p<32) {char b[7];sprintf_s(b,"\\u%04x",unsigned(*p));out+=b;}
  else out+=char(*p);
 }
 return out;
}
static void record(const char* event,const std::string& value="") noexcept {
 try {std::lock_guard<std::mutex> guard(log_mutex);std::ofstream f(log_path,std::ios::app);
 f<<"{\"tick_ms\":"<<GetTickCount64()<<",\"thread\":"<<GetCurrentThreadId()<<",\"event\":\""<<event<<"\",\"value\":\""<<escape(value.c_str())<<"\"}\n";
 } catch(...) {} // Observation failure must not throw into the host.
}
BOOL WINAPI DllMain(HINSTANCE h,DWORD reason,LPVOID){if(reason==DLL_PROCESS_ATTACH)module_handle=h;return TRUE;}
extern "C" __declspec(dllexport) DWORD RequiredVersion(){return 2010900;}
extern "C" __declspec(dllexport) COMMON_PLUGIN_TABLE* GetCommonPluginTable(){return &table;}
extern "C" __declspec(dllexport) bool InitializePlugin(DWORD version){
 try {wchar_t p[32768];auto n=GetModuleFileNameW(module_handle,p,32768);if(!n||n==32768)return false;
 log_path=std::filesystem::path(p).parent_path()/L"clipchannel-edit-probe.jsonl";
 session=std::to_string(GetCurrentProcessId())+"-"+std::to_string(GetTickCount64());
 record("initialize",std::to_string(version));return true;}catch(...){return false;}
}
extern "C" __declspec(dllexport) void UninitializePlugin(){record("uninitialize");}
static void loaded(PROJECT_FILE* p){record("load_marker",p->get_param_string("validation_marker")?p->get_param_string("validation_marker"):"<absent>");}
static void saving(PROJECT_FILE* p){auto marker=session+"-"+std::to_string(++save_sequence);p->set_param_string("validation_marker",marker.c_str());record("save_before",marker);}
static void updated(void*){record("update_object");}
static void scene_changed(void*){record("change_scene");}
static void snapshot(void*){record("edit_state",std::to_string(edit_handle->get_edit_state()));}
static void apply_fixture(void*) {
 record("request_begin");
 bool invoked=edit_handle->call_edit_section([](EDIT_SECTION* edit){
  auto p=edit->get_project_file(edit_handle);auto path=p->get_project_file_path();
  if(!path || std::filesystem::path(path).filename()!=L"sdk-edit-probe.aup2") {record("refused","fixture filename mismatch");return;}
  auto a=edit->find_object(1,0),b=edit->find_object(1,120);
  if(!a||!b||a==b||edit->count_object_effect(a,L"テキスト")!=1||edit->count_object_effect(b,L"テキスト")!=1){record("refused","fixture objects mismatch");return;}
  auto value=[&](OBJECT_HANDLE o,LPCWSTR key){auto s=edit->get_object_item_value(o,L"標準描画",key);return std::string(s?s:"");};
  if(value(a,L"X")!="10.00"||value(b,L"X")!="0.00"||value(a,L"Y")!="60.00"){record("refused","fixture values mismatch");return;}
  auto alias=[&](const char* tag,OBJECT_HANDLE o){auto s=edit->get_object_alias(o);record(tag,s?s:"<missing>");};
  alias("before_a",a);alias("before_b",b);
  bool ok_a=edit->set_object_item_value(a,L"標準描画",L"X","20.00");
  bool ok_b=ok_a&&edit->set_object_item_value(b,L"標準描画",L"X","30.00");
  alias("after_a",a);alias("after_b",b);
  record("set_results",std::string(ok_a?"1":"0")+","+(ok_b?"1":"0"));
 });
 record("request_return",invoked?"1":"0");
}
extern "C" __declspec(dllexport) void RegisterPlugin(HOST_APP_TABLE* host){
 edit_handle=host->create_edit_handle();
 host->register_project_load_handler(loaded);host->register_project_save_handler(saving);
 host->register_event_listener(EVENT_TYPE::UPDATE_OBJECT,nullptr,updated);
 host->register_event_listener(EVENT_TYPE::CHANGE_EDIT_SCENE,nullptr,scene_changed);
 host->register_edit_menu_param(L"Validation Observer\\Record state",nullptr,snapshot);
 host->register_edit_menu_param(L"SDK Edit Probe\\Apply fixture",nullptr,apply_fixture); record("registered");
}

