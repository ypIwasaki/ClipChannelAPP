// THROWAWAY v5. Fixed fixture only; no production integration or hidden host commands.
#include <windows.h>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <string>
#include <map>
#include <atomic>
#include "plugin2.h"
#include "output2.h"
static HMODULE module_handle;
static EDIT_HANDLE* edit;
static std::filesystem::path log_path;
static std::mutex log_mutex, save_mutex;
static std::atomic<unsigned long long> revision{0}, sequence{0};
static std::string session;
static COMMON_PLUGIN_TABLE table={L"ClipChannel Transaction Probe",L"Throwaway transaction probe v5"};
static std::string escape(const std::string& s){std::string r;for(unsigned char c:s){if(c=='"'||c=='\\'){r+='\\';r+=char(c);}else if(c<32){char b[7];sprintf_s(b,"\\u%04x",unsigned(c));r+=b;}else r+=char(c);}return r;}
static bool record(const char* name,const std::string& s="") noexcept {try{std::lock_guard<std::mutex> g(log_mutex);std::ofstream f(log_path,std::ios::app);f<<"{\"tick_ms\":"<<GetTickCount64()<<",\"event\":\""<<name<<"\",\"value\":\""<<escape(s)<<"\"}\n";f.flush();return bool(f);}catch(...){return false;}}
static std::string read_file(const std::filesystem::path& p){std::ifstream f(p,std::ios::binary);return std::string(std::istreambuf_iterator<char>(f),{});}
// This deliberately includes the empty sixth layer, but not unexposed group metadata.
// Saved aup2 comparison remains required for complete recovery, not this snapshot alone.
static std::string capture(EDIT_SECTION* e){
 std::string result;
 for(int layer=0;layer<6;layer++){int start=0;
  for(int n=0;n<20;n++){
   auto o=e->find_object(layer,start);if(!o)break;
   auto f=e->get_object_layer_frame(o);if(f.layer!=layer||f.start<start||f.end<f.start)return "INVALID";
   result+="ITEM "+std::to_string(layer)+" "+std::to_string(f.start)+" "+std::to_string(f.end)+"\n";
   auto a=e->get_object_alias(o);if(!a)return "INVALID";result+=a;start=f.end+1;
  }
 }
 return result;
}
static std::string snapshot(){std::string s="INVALID";bool ok=edit->call_read_section_param(&s,[](void* p,EDIT_SECTION* e){*(std::string*)p=capture(e);});return ok?s:"UNAVAILABLE";}
static bool fixture(EDIT_SECTION* e){auto p=e->get_project_file(edit)->get_project_file_path();return p&&std::filesystem::path(p).filename()==L"transaction-fixture.aup2";}
struct Save{std::string snapshot;unsigned long long rev;};
static std::map<std::string,Save> saves;
static void saving(PROJECT_FILE* p){
 auto marker=session+"-"+std::to_string(++sequence);
 auto s=snapshot();auto rev=revision.load();p->set_param_string("transaction_marker",marker.c_str());
 {std::lock_guard<std::mutex> g(save_mutex);saves[marker]={s,rev};}
 record("save_candidate",marker);record("save_snapshot",s);
}
static void loaded(PROJECT_FILE*){++revision;record("load");}
static void updated(void*){++revision;record("update",std::to_string(revision.load()));}
static std::string armed_marker,armed_snapshot,armed_bytes;
static std::filesystem::path armed_path;
static unsigned long long armed_revision=0;
static void arm(void*){
 armed_marker.clear();std::filesystem::path path;
 edit->call_edit_section_param(&path,[](void* p,EDIT_SECTION* e){if(fixture(e)){auto s=e->get_project_file(edit)->get_project_file_path();if(s)*(std::filesystem::path*)p=s;}});
 if(path.empty()){record("arm_rejected","wrong fixture");return;}
 auto bytes=read_file(path);auto at=bytes.find("transaction_marker=");
 if(at==std::string::npos){record("arm_rejected","no disk marker");return;}
 at+=19;auto end=bytes.find_first_of("\r\n",at);auto marker=bytes.substr(at,end-at);
 Save saved;{std::lock_guard<std::mutex> g(save_mutex);auto it=saves.find(marker);if(it==saves.end()){record("arm_rejected","marker from another session");return;}saved=it->second;}
 auto current=snapshot();
 if(current=="INVALID"||current=="UNAVAILABLE"||current!=saved.snapshot||revision.load()!=saved.rev){record("arm_rejected","saved state differs or capture unavailable");return;}
 armed_snapshot=current;armed_bytes=bytes;armed_path=path;armed_revision=revision.load();armed_marker=marker;
 record("armed",marker);
}
// Own modal UI, not UI automation of the host. The modal message loop keeps input
// responsive while Windows disables its owner. It does not intercept other plugins.
static std::string modal_before;
static bool compound_used=false;
static INT_PTR CALLBACK dialog_proc(HWND h,UINT msg,WPARAM w,LPARAM){
 if(msg==WM_INITDIALOG){
  CreateWindowW(L"STATIC",L"Validation only. Owner input is disabled.\nApply creates one image and deletes the grouped caption.\nClose returns control; host Undo is tested separately.",WS_CHILD|WS_VISIBLE,12,12,490,60,h,nullptr,module_handle,nullptr);
  CreateWindowW(L"BUTTON",L"Apply create + delete",WS_CHILD|WS_VISIBLE|WS_TABSTOP,12,86,190,30,h,(HMENU)100,module_handle,nullptr);
  CreateWindowW(L"BUTTON",L"Close waiting screen",WS_CHILD|WS_VISIBLE|WS_TABSTOP,222,86,190,30,h,(HMENU)101,module_handle,nullptr);
  modal_before=snapshot();record("modal_begin",modal_before);SetTimer(h,1,1000,nullptr);return TRUE;
 }
 if(msg==WM_TIMER){record("modal_sample",snapshot());return TRUE;}
 if(msg==WM_COMMAND&&LOWORD(w)==100){
  if(compound_used)return TRUE;
  bool ok=edit->call_edit_section([](EDIT_SECTION* e){
   if(!fixture(e)||e->find_object(5,0))return;
   auto target=e->find_object(1,120);auto image=e->find_object(2,0);if(!target||!image)return;
   auto f=e->get_object_layer_frame(target);if(f.start!=120||f.end!=239)return;
   auto a=e->get_object_alias(image);if(!a)return;std::string alias=a;
   if(!record("compound_before",capture(e)))return;
   auto created=e->create_object_from_alias(alias.c_str(),5,0,120);if(!created){record("compound_refused","creation failed");return;}
   compound_used=true;e->delete_object(target);record("compound_after",capture(e));
  });record("compound_return",ok?"1":"0");EnableWindow(GetDlgItem(h,100),FALSE);return TRUE;
 }
 if(msg==WM_COMMAND&&LOWORD(w)==101){KillTimer(h,1);record("modal_end",snapshot());EndDialog(h,0);return TRUE;}
 if(msg==WM_CLOSE)return TRUE; // explicit release button keeps the end boundary observable
 return FALSE;
}
static void modal(void*){
 bool valid=false;edit->call_edit_section_param(&valid,[](void* p,EDIT_SECTION* e){*(bool*)p=fixture(e);});if(!valid){record("refused","wrong fixture");return;}
 struct Template{DLGTEMPLATE dialog;WORD menu,window_class,title;};
 Template t={};t.dialog.style=WS_POPUP|WS_CAPTION|WS_SYSMENU|DS_MODALFRAME;t.dialog.x=30;t.dialog.y=30;t.dialog.cx=290;t.dialog.cy=85;
 auto r=DialogBoxIndirectParamW(module_handle,&t.dialog,edit->get_host_app_window(),dialog_proc,0);record("modal_return",std::to_string(r));
}
static bool output(OUTPUT_INFO* info){
 record("output_enter",std::to_string(edit->get_edit_state()));
 auto current=snapshot();record("output_entry_snapshot",current);
 if(armed_marker.empty()||current=="INVALID"||current=="UNAVAILABLE"||current!=armed_snapshot||revision.load()!=armed_revision||read_file(armed_path)!=armed_bytes){record("output_rejected","cannot prove exact armed state");return false;}
 // This receipt proves callback access only, not general group/scene equality or video encoding.
 if(!info->savefile||std::filesystem::exists(info->savefile)||info->w!=320||info->h!=180||info->n!=360){record("output_rejected","unexpected output");return false;}
 unsigned long long hash=14695981039346656037ull;
 for(int i=0;i<info->n;i++){
  if(info->func_is_abort()){record("output_cancelled");return false;}
  if(revision.load()!=armed_revision){record("output_rejected","late update");return false;}
  auto data=(unsigned char*)info->func_get_video(i,0);if(!data){record("output_rejected","render failed");return false;}
  for(int j=0;j<info->w*info->h*3;j++){hash^=data[j];hash*=1099511628211ull;}info->func_rest_time_disp(i,info->n);
 }
 if(revision.load()!=armed_revision||read_file(armed_path)!=armed_bytes){record("output_rejected","late state change");return false;}
 std::ofstream f(std::filesystem::path(info->savefile),std::ios::binary);f<<"PROBE ONLY\nmarker="<<armed_marker<<"\nframes="<<info->n<<"\nchecksum="<<hash<<"\n";f.flush();record("output_receipt",f?"success":"write-failed");return bool(f);
}
static OUTPUT_PLUGIN_TABLE output_table={OUTPUT_PLUGIN_TABLE::FLAG_VIDEO,L"ClipChannel transaction state probe",L"Probe receipt (*.cctx)\0*.cctx\0\0",L"Throwaway callback gate",output,nullptr,nullptr,nullptr,nullptr};
BOOL WINAPI DllMain(HINSTANCE h,DWORD reason,LPVOID){if(reason==DLL_PROCESS_ATTACH)module_handle=h;return TRUE;}
extern "C" __declspec(dllexport) DWORD RequiredVersion(){return 2010900;}
extern "C" __declspec(dllexport) COMMON_PLUGIN_TABLE* GetCommonPluginTable(){return &table;}
extern "C" __declspec(dllexport) bool InitializePlugin(DWORD version){wchar_t p[32768];auto n=GetModuleFileNameW(module_handle,p,32768);if(!n||n==32768)return false;log_path=std::filesystem::path(p).parent_path()/L"clipchannel-transaction.jsonl";session=std::to_string(GetCurrentProcessId())+"-"+std::to_string(GetTickCount64());record("initialize",std::to_string(version));return true;}
extern "C" __declspec(dllexport) void UninitializePlugin(){record("uninitialize");}
extern "C" __declspec(dllexport) void RegisterPlugin(HOST_APP_TABLE* host){
 edit=host->create_edit_handle();host->register_project_save_handler(saving);host->register_project_load_handler(loaded);
 host->register_event_listener(EVENT_TYPE::UPDATE_OBJECT,nullptr,updated);host->register_event_listener(EVENT_TYPE::CHANGE_EDIT_SCENE,nullptr,updated);
 host->register_edit_menu_param(L"Transaction Probe\\Open waiting screen",nullptr,modal);
 host->register_edit_menu_param(L"Transaction Probe\\Capture",nullptr,[](void*){record("capture",snapshot());});
 host->register_edit_menu_param(L"Transaction Probe\\Arm saved disk state",nullptr,arm);
 host->register_output_plugin(&output_table);record("registered");
}
