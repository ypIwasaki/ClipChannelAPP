// THROWAWAY validation observer, not a product integration plugin.
// Never edits objects or invokes host commands. Saves only its own probe marker.
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
static COMMON_PLUGIN_TABLE table={L"ClipChannel Validation Observer",L"Throwaway SDK observer v1 - events and save marker only"};
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
 log_path=std::filesystem::path(p).parent_path()/L"clipchannel-observer.jsonl";
 session=std::to_string(GetCurrentProcessId())+"-"+std::to_string(GetTickCount64());
 record("initialize",std::to_string(version));return true;}catch(...){return false;}
}
extern "C" __declspec(dllexport) void UninitializePlugin(){record("uninitialize");}
static void loaded(PROJECT_FILE* p){record("load_marker",p->get_param_string("validation_marker")?p->get_param_string("validation_marker"):"<absent>");}
static void saving(PROJECT_FILE* p){auto marker=session+"-"+std::to_string(++save_sequence);p->set_param_string("validation_marker",marker.c_str());record("save_before",marker);}
static void updated(void*){record("update_object");}
static void scene_changed(void*){record("change_scene");}
static void snapshot(void*){record("edit_state",std::to_string(edit_handle->get_edit_state()));}
extern "C" __declspec(dllexport) void RegisterPlugin(HOST_APP_TABLE* host){
 edit_handle=host->create_edit_handle();
 host->register_project_load_handler(loaded);host->register_project_save_handler(saving);
 host->register_event_listener(EVENT_TYPE::UPDATE_OBJECT,nullptr,updated);
 host->register_event_listener(EVENT_TYPE::CHANGE_EDIT_SCENE,nullptr,scene_changed);
 host->register_edit_menu_param(L"Validation Observer\\Record state",nullptr,snapshot);
 record("registered");
}
