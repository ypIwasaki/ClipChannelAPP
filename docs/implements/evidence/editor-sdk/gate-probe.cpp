// THROWAWAY validation observer, not a product integration plugin.
// v3 gate probe: bounded output-state observer and one explicit reversible failure fixture.
#include <windows.h>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <string>
#include <thread>
#include <atomic>
#include <chrono>
#include <vector>
#include "plugin2.h"
static HMODULE module_handle;
static std::filesystem::path log_path;
static std::mutex log_mutex;
static EDIT_HANDLE* edit_handle;
static unsigned long long save_sequence=0;
static std::string session;
static COMMON_PLUGIN_TABLE table={L"ClipChannel Gate Probe",L"Throwaway E2 E4 E5 gate probe v3"};
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
static bool record(const char* event,const std::string& value="") noexcept {
 try {std::lock_guard<std::mutex> guard(log_mutex);std::ofstream f(log_path,std::ios::app);
 f<<"{\"tick_ms\":"<<GetTickCount64()<<",\"thread\":"<<GetCurrentThreadId()<<",\"event\":\""<<event<<"\",\"value\":\""<<escape(value.c_str())<<"\"}\n";
  f.flush(); return bool(f); } catch(...) {return false;} // Do not throw into host.
}
BOOL WINAPI DllMain(HINSTANCE h,DWORD reason,LPVOID){if(reason==DLL_PROCESS_ATTACH)module_handle=h;return TRUE;}
extern "C" __declspec(dllexport) DWORD RequiredVersion(){return 2010900;}
extern "C" __declspec(dllexport) COMMON_PLUGIN_TABLE* GetCommonPluginTable(){return &table;}
extern "C" __declspec(dllexport) bool InitializePlugin(DWORD version){
 try {wchar_t p[32768];auto n=GetModuleFileNameW(module_handle,p,32768);if(!n||n==32768)return false;
 log_path=std::filesystem::path(p).parent_path()/L"clipchannel-gates.jsonl";
 session=std::to_string(GetCurrentProcessId())+"-"+std::to_string(GetTickCount64());
 record("initialize",std::to_string(version));return true;}catch(...){return false;}
}
static std::thread watcher; static std::atomic<bool> stop_watch{false},watch_done{true}; static bool failure_used=false;
extern "C" __declspec(dllexport) void UninitializePlugin(){stop_watch=true;if(watcher.joinable())watcher.join();record("uninitialize");}
static void loaded(PROJECT_FILE* p){record("load_marker",p->get_param_string("validation_marker")?p->get_param_string("validation_marker"):"<absent>");}
static void saving(PROJECT_FILE* p){auto marker=session+"-"+std::to_string(++save_sequence);p->set_param_string("validation_marker",marker.c_str());record("save_before",marker);}
static void updated(void*){record("update_object");}
static void scene_changed(void*){record("change_scene");}
static void snapshot(void*){record("edit_state",std::to_string(edit_handle->get_edit_state()));}
static std::string capture(EDIT_SECTION* e) {
 std::string s;
 const int layers[]={0,0,0,1,1,1,2,3},frames[]={0,120,240,0,120,240,0,60};
 for(int i=0;i<8;i++){
  auto o=e->find_object(layers[i],frames[i]);if(!o)return "INVALID";
  auto f=e->get_object_layer_frame(o);if(f.layer!=layers[i]||f.start!=frames[i])return "INVALID";
  s+="ITEM "+std::to_string(i)+" "+std::to_string(f.layer)+" "+std::to_string(f.start)+" "+std::to_string(f.end)+"\n";
  auto a=e->get_object_alias(o);if(!a)return "INVALID";s+=a;
 }
 return s;
}
static bool fixture(EDIT_SECTION* e){
 auto p=e->get_project_file(edit_handle);auto path=p->get_project_file_path();
 return path&&std::filesystem::path(path).filename()==L"gate-fixture.aup2";
}
static void capture_menu(void*){
 bool ok=edit_handle->call_read_section([](EDIT_SECTION* e){record("snapshot",capture(e));});
 record("snapshot_return",ok?"1":"0");
}
static void fail_restore(void*){
 if(failure_used){record("refused","failure case already used in this process");return;}
 bool invoked=edit_handle->call_edit_section([](EDIT_SECTION* e){
  if(!fixture(e)){record("refused","wrong fixture");return;}
  auto caption=e->find_object(1,0),audio=e->find_object(3,60);
  if(!caption||!audio){record("refused","objects missing");return;}
  auto value=[&](OBJECT_HANDLE o,LPCWSTR effect,LPCWSTR key){auto p=e->get_object_item_value(o,effect,key);return std::string(p?p:"");};
  auto x=value(caption,L"標準描画",L"X"),y=value(caption,L"標準描画",L"Y"),vol=value(audio,L"音声再生",L"音量");
  auto before=capture(e);
  if(x!="0.00"||y!="60.00"||vol!="15.00"||before=="INVALID"){record("refused","fixture preconditions mismatch");return;}
  // Flush restoration evidence before the first mutation.
  if(!record("recovery_before",before)){return;}
  failure_used=true;
  bool a=e->set_object_item_value(caption,L"標準描画",L"X","20.00");
  bool b=a&&e->set_object_item_value(audio,L"音声再生",L"音量","30.00");
  record("partial_state",capture(e));
  record("injected_failure",a&&b?"after two successful changes; third step skipped":"unexpected setter failure");
  bool rb=e->set_object_item_value(audio,L"音声再生",L"音量",vol.c_str());
  bool ra=e->set_object_item_value(caption,L"標準描画",L"X",x.c_str());
  auto after=capture(e);record("recovery_after",after);
  record("recovery_result",ra&&rb&&before==after?"restored":"blocked-retain-evidence");
 });record("failure_section_return",invoked?"1":"0");
}
static void arm_watch(void*){
 if(!watch_done){record("refused","watch already active");return;}
 if(watcher.joinable())watcher.join();stop_watch=false;watch_done=false;
 watcher=std::thread([]{
  record("watch_start");int previous=-1;bool observed=false;
  for(int i=0;i<1200&&!stop_watch;i++){
   int state=edit_handle->get_edit_state();
   if(state!=previous){record("output_state",std::to_string(state));previous=state;}
   if(state==EDIT_HANDLE::EDIT_STATE_SAVE&&!observed){
    observed=true;
    // Deliberately no mutation even if the host unexpectedly accepts the call.
    bool accepted=edit_handle->call_edit_section([](EDIT_SECTION*){record("output_noop_callback");});
    record("output_edit_section_accepted",accepted?"1":"0");
   }
   if(observed&&state==EDIT_HANDLE::EDIT_STATE_EDIT)break;
   std::this_thread::sleep_for(std::chrono::milliseconds(100));
  }
  record("watch_end",observed?"output-observed":"timeout-no-output");watch_done=true;
 });
}
extern "C" __declspec(dllexport) void RegisterPlugin(HOST_APP_TABLE* host){
 edit_handle=host->create_edit_handle();
 host->register_project_load_handler(loaded);host->register_project_save_handler(saving);
 host->register_event_listener(EVENT_TYPE::UPDATE_OBJECT,nullptr,updated);
 host->register_event_listener(EVENT_TYPE::CHANGE_EDIT_SCENE,nullptr,scene_changed);
 host->register_edit_menu_param(L"Validation Observer\\Record state",nullptr,snapshot);
 host->register_edit_menu_param(L"Gate Probe\\Capture",nullptr,capture_menu); host->register_edit_menu_param(L"Gate Probe\\Fail and restore ONCE",nullptr,fail_restore); host->register_edit_menu_param(L"Gate Probe\\Watch next output (120s)",nullptr,arm_watch); record("registered");
}

