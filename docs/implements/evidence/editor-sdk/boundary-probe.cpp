// THROWAWAY validation observer, not a product integration plugin.
// v4: bounded lock observation, normal object round trips, and output-entry revision guard.
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
#include "output2.h"
static HMODULE module_handle;
static std::filesystem::path log_path;
static std::mutex log_mutex;
static EDIT_HANDLE* edit_handle;
static unsigned long long save_sequence=0;
static std::string session;
static COMMON_PLUGIN_TABLE table={L"ClipChannel Boundary Probe",L"Throwaway boundary probe v4"};
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
 log_path=std::filesystem::path(p).parent_path()/L"clipchannel-boundary.jsonl";
 session=std::to_string(GetCurrentProcessId())+"-"+std::to_string(GetTickCount64());
 record("initialize",std::to_string(version));return true;}catch(...){return false;}
}
static std::thread watcher; static std::atomic<bool> stop_watch{false},watch_done{true}; static bool failure_used=false;
extern "C" __declspec(dllexport) void UninitializePlugin(){stop_watch=true;if(watcher.joinable())watcher.join();record("uninitialize");}
static std::atomic<unsigned long long> revision{0};
static std::mutex saved_mutex;
static std::string saved_marker; static std::filesystem::path saved_path; static unsigned long long saved_revision=0;
static void loaded(PROJECT_FILE* p){++revision;record("load_marker",p->get_param_string("validation_marker")?p->get_param_string("validation_marker"):"<absent>");}
static void saving(PROJECT_FILE* p){auto marker=session+"-"+std::to_string(++save_sequence);p->set_param_string("validation_marker",marker.c_str());record("save_before",marker); std::lock_guard<std::mutex> g(saved_mutex); saved_marker=marker; saved_revision=revision.load(); auto path=p->get_project_file_path(); saved_path=path?path:L"";}
static void updated(void*){++revision;record("update_object");}
static void scene_changed(void*){++revision;record("change_scene");}

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
 return path&&std::filesystem::path(path).filename()==L"boundary-fixture.aup2";
}
static void capture_menu(void*){
 bool ok=edit_handle->call_read_section([](EDIT_SECTION* e){record("snapshot",capture(e));});
 record("snapshot_return",ok?"1":"0");
}
// Normal reversible SDK round trips; no new injected failure.
static bool roundtrip_used=false,created_used=false;
static OBJECT_HANDLE pending_created=nullptr; static std::string pending_alias;
static void hold_section(void*) {
 edit_handle->call_edit_section([](EDIT_SECTION* e){
  if(!fixture(e)){record("refused","wrong fixture");return;}
  auto before=capture(e); if(before=="INVALID")return;
  record("hold_begin",before);
  std::this_thread::sleep_for(std::chrono::seconds(20));
  record("hold_end",capture(e));
 });record("hold_return");
}
static void roundtrip(void*) {
 if(roundtrip_used){record("refused","round trip already used");return;}
 edit_handle->call_edit_section([](EDIT_SECTION* e){
  if(!fixture(e))return;
  auto o=e->find_object(1,120);if(!o)return;
  auto f=e->get_object_layer_frame(o);if(f.layer!=1||f.start!=120||f.end!=239)return;
  auto raw=e->get_object_alias(o);if(!raw)return;std::string alias=raw;
  if(!record("delete_recovery_alias",alias)||!record("roundtrip_before",capture(e)))return;
  roundtrip_used=true;
  e->delete_object(o); record("deleted_state",capture(e));
  auto restored=e->create_object_from_alias(alias.c_str(),f.layer,f.start,f.end-f.start+1);
  record("recreated",restored?"1":"0");record("roundtrip_after",capture(e));
 });
}
static void create_fixture_object(void*) {
 if(created_used||pending_created)return;
 edit_handle->call_edit_section([](EDIT_SECTION* e){
  if(!fixture(e)||e->find_object(5,0))return;
  auto source=e->find_object(2,0);if(!source)return;
  auto raw=e->get_object_alias(source);if(!raw)return;std::string alias=raw;
  if(!record("create_before",capture(e)))return;
  pending_created=e->create_object_from_alias(alias.c_str(),5,0,120);
  created_used=true;
  if(pending_created){auto p=e->get_object_alias(pending_created);pending_alias=p?p:"";}
  record("created",pending_created?"1":"0");
 });
}
static void remove_created_object(void*) {
 // Explicit second edit section: SDK forbids deleting an object in its creating section.
 edit_handle->call_edit_section([](EDIT_SECTION* e){
  if(!fixture(e)||!pending_created)return;
  auto o=e->find_object(5,0);if(!o||o!=pending_created)return;
  auto p=e->get_object_alias(o);if(!p||pending_alias!=p){record("refused","temporary object changed");return;}
  e->delete_object(o);pending_created=nullptr;
  record("temporary_removed",e->find_object(5,0)?"0":"1");record("create_roundtrip_after",capture(e));
 });
}
static bool guarded_output(OUTPUT_INFO* info) {
 std::string marker;std::filesystem::path path;unsigned long long rev;
 {std::lock_guard<std::mutex> g(saved_mutex);marker=saved_marker;path=saved_path;rev=saved_revision;}
 record("output_gate_enter",std::to_string(revision.load()));
 if(path.filename()!=L"boundary-fixture.aup2"||marker.empty()||revision.load()!=rev){record("output_rejected","unsaved change or missing save");return false;}
 std::ifstream f(path,std::ios::binary);std::string bytes((std::istreambuf_iterator<char>(f)),{});
 if(!f||bytes.find("validation_marker="+marker)==std::string::npos){record("output_rejected","save marker absent on disk");return false;}
 // Produce a frame checksum receipt, NOT a finished video. Never overwrite an existing file.
 if(!info->savefile||std::filesystem::exists(info->savefile)){record("output_rejected","destination exists or missing");return false;}
 if(info->w!=320||info->h!=180||info->n!=360){record("output_rejected","unexpected fixture dimensions");return false;}
 unsigned long long checksum=14695981039346656037ull;
 for(int i=0;i<info->n;i++){
  if(info->func_is_abort()||revision.load()!=rev){record("output_rejected","cancel or concurrent update");return false;}
  auto data=(unsigned char*)info->func_get_video(i,0);if(!data){record("output_rejected","frame unavailable");return false;}
  for(int n=0;n<info->w*info->h*3;n++){checksum^=data[n];checksum*=1099511628211ull;}
  info->func_rest_time_disp(i,info->n);
 }
 if(revision.load()!=rev){record("output_rejected","late update");return false;}
 std::ofstream receipt(std::filesystem::path(info->savefile),std::ios::binary);
 receipt<<"THROWAWAY FRAME RECEIPT, NOT VIDEO\nmarker="<<marker<<"\nframes="<<info->n<<"\nchecksum="<<checksum<<"\n";receipt.flush();
 record("output_receipt",receipt?"success":"write-failed");return bool(receipt);
}
static OUTPUT_PLUGIN_TABLE output_table={OUTPUT_PLUGIN_TABLE::FLAG_VIDEO,L"ClipChannel saved-state guard probe",L"Probe receipt (*.ccprobe)\0*.ccprobe\0\0",L"Validation receipt only; not a video encoder",guarded_output,nullptr,nullptr,nullptr,nullptr};
extern "C" __declspec(dllexport) void RegisterPlugin(HOST_APP_TABLE* host){
 edit_handle=host->create_edit_handle();
 host->register_project_load_handler(loaded);host->register_project_save_handler(saving);
 host->register_event_listener(EVENT_TYPE::UPDATE_OBJECT,nullptr,updated);
 host->register_event_listener(EVENT_TYPE::CHANGE_EDIT_SCENE,nullptr,scene_changed);
 host->register_edit_menu_param(L"Boundary Probe\\Capture",nullptr,capture_menu);
 host->register_edit_menu_param(L"Boundary Probe\\Hold edit section 20s",nullptr,hold_section);
 host->register_edit_menu_param(L"Boundary Probe\\Delete and recreate grouped caption",nullptr,roundtrip);
 host->register_edit_menu_param(L"Boundary Probe\\Create temporary image",nullptr,create_fixture_object);
 host->register_edit_menu_param(L"Boundary Probe\\Remove temporary image",nullptr,remove_created_object);
 host->register_output_plugin(&output_table);record("registered");
}
