(function(global) {
'use strict';
const clone = value => JSON.parse(JSON.stringify(value));
const DEFAULT_CATEGORIES=[{id:'ca-nhan',name:'Cá nhân',color:'#f36e77'},{id:'devops',name:'DevOps',color:'#67c5d3'},{id:'hoc-tap',name:'Học tập',color:'#ecc64c'}];
const categoryNameKey=value=>normalize(value.trim().replace(/\s+/g,' '));
const PRIORITIES = {1:'Cao',2:'Trung bình',3:'Thấp'};
const dateKey = value => {const d=new Date(value);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};
const parseDay = value => new Date(`${value}T12:00:00`);
const plusDays = (value,n) => {const d=parseDay(value);d.setDate(d.getDate()+n);return dateKey(d);};
const todayKey = () => dateKey(new Date());
const monday = value => {const d=parseDay(value);return plusDays(value,-((d.getDay()+6)%7));};
const normalize = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[đĐ]/g,'d').toLocaleLowerCase('vi');
const uuid = () => {const b=new Uint8Array(16);global.crypto.getRandomValues(b);b[6]=(b[6]&15)|64;b[8]=(b[8]&63)|128;const s=Array.from(b,x=>x.toString(16).padStart(2,'0')).join('');return `${s.slice(0,8)}-${s.slice(8,12)}-${s.slice(12,16)}-${s.slice(16,20)}-${s.slice(20)}`;};
const emptyState = (tasks,categories=DEFAULT_CATEGORIES) => ({schema:1,serverTasks:clone(tasks),categories:clone(categories),deletedCategories:[],queue:[],lastSynced:null,lease:null});
function project(snapshot) {
  const map=new Map(snapshot.serverTasks.map(task=>[task.client_id,{...clone(task),pending:false}]));
  for(const op of snapshot.queue) {
    const old=map.get(op.client_id);
    if(op.type==='create') map.set(op.client_id,{id:null,client_id:op.client_id,due_date:null,due_time:null,priority:0,tags:[],completed:false,local_order:op.created_at,...old,...clone(op.payload),pending:true});
    else if(op.type==='update'&&old) map.set(op.client_id,{...old,...clone(op.payload),pending:true});
    else if(op.type==='delete') map.delete(op.client_id);
  }
  const active=new Set(projectCategories(snapshot).map(c=>c.id));
  return Array.from(map.values(),task=>({...task,tags:(task.tags||[]).filter(tag=>active.has(tag))}));
}
function projectCategories(snapshot){
  const categories=new Map((snapshot.categories||DEFAULT_CATEGORIES).map(c=>[c.id,{...clone(c),pending:false}]));
  const deleted=new Set(snapshot.deletedCategories||[]);
  for(const op of snapshot.queue){
    if(op.type==='category_create'&&!deleted.has(op.client_id))categories.set(op.client_id,{id:op.client_id,...clone(op.payload),pending:true});
    if(op.type==='category_delete'){deleted.add(op.client_id);categories.delete(op.client_id);}
  }
  return Array.from(categories.values()).filter(c=>!deleted.has(c.id));
}
function visibleTasks(tasks,view,selectedDate,query,order,today=todayKey(),tag=null) {
  const needle=normalize(query.trim());
  const collator=new Intl.Collator('vi',{sensitivity:'base',numeric:true});
  return tasks.filter(task=> {
    if(needle&&!normalize(task.title).includes(needle))return false;
    if(tag&&!(task.tags||[]).includes(tag))return false;
    if(view==='today')return task.due_date===today;
    if(view==='upcoming')return Boolean(task.due_date&&task.due_date>=today);
    if(view==='calendar')return task.due_date===(selectedDate||today);
    return true;
  }).sort((a,b)=> {
    if(a.completed!==b.completed)return Number(a.completed)-Number(b.completed);
    if(order==='name')return collator.compare(a.title,b.title)||((a.id||0)-(b.id||0));
    if(order==='due')return (a.due_date||'9999').localeCompare(b.due_date||'9999')||(a.due_time||'23:59').localeCompare(b.due_time||'23:59');
    if(order==='priority')return (a.priority||4)-(b.priority||4)||(a.due_date||'9999').localeCompare(b.due_date||'9999');
    const av=a.id===null?1e12+Date.parse(a.local_order||0):a.id;
    const bv=b.id===null?1e12+Date.parse(b.local_order||0):b.id;
    return order==='oldest'?av-bv:bv-av;
  });
}
function upcomingGroups(tasks,today=todayKey()) {
  const tomorrow=plusDays(today,1),start=plusDays(today,2),end=plusDays(monday(today),6);
  const remainingWeek=start<=end;
  const groups=[
    {key:'today',title:'Hôm nay',date:today,tasks:tasks.filter(t=>t.due_date===today)},
    {key:'tomorrow',title:'Ngày mai',date:tomorrow,tasks:tasks.filter(t=>t.due_date===tomorrow)},
    {key:remainingWeek?'week':'later',title:remainingWeek?'Trong tuần':'Sau đó',date:start,tasks:tasks.filter(t=>t.due_date>tomorrow&&(!remainingWeek||t.due_date<=end))}
  ];
  if(remainingWeek){const later=tasks.filter(t=>t.due_date>end);if(later.length)groups.push({key:'later',title:'Sau tuần này',date:plusDays(end,1),tasks:later});}
  return groups;
}
function connectionStatus(state,pending) {
  if(state.storageError)return {text:'Chưa lưu được thay đổi trên thiết bị',status:'error'};
  if(state.syncing)return {text:'Đang kết nối và đồng bộ',status:'pending'};
  if(state.health==='waiting')return {text:'Đang đồng bộ ở thẻ trình duyệt khác',status:'pending'};
  if(state.health==='offline')return {text:'Chế độ ngoại tuyến · Lưu trên thiết bị',status:'offline'};
  if(state.health==='unavailable')return {text:'Không kết nối được máy chủ',status:'offline'};
  if(state.health==='error')return {text:'Không thể đồng bộ · Cần kiểm tra',status:'error'};
  if(state.health==='online'&&!pending)return {text:'Trực tuyến · Đã đồng bộ',status:'online'};
  if(state.health==='online')return {text:'Trực tuyến · Có thay đổi chờ gửi',status:'pending'};
  return {text:'Chưa xác nhận kết nối máy chủ',status:'pending'};
}
function acknowledge(snapshot,opId,result) {
  if(!snapshot.queue.some(op=>op.op_id===opId))return;
  snapshot.queue=snapshot.queue.filter(op=>op.op_id!==opId);
  if(result.category_deleted){
    const id=result.client_id;
    snapshot.deletedCategories=Array.from(new Set([...(snapshot.deletedCategories||[]),id]));
    snapshot.categories=(snapshot.categories||DEFAULT_CATEGORIES).filter(c=>c.id!==id);
    snapshot.serverTasks.forEach(task=>{task.tags=(task.tags||[]).filter(tag=>tag!==id);});
    // Keep queued request payloads unchanged: a response may have been lost.
    return;
  }
  if(result.category){
    const category=result.category,from=result.client_id,to=category.id;
    snapshot.categories=(snapshot.categories||DEFAULT_CATEGORIES).filter(c=>c.id!==from&&c.id!==to);snapshot.categories.push(clone(category));
    if(from!==to){
      const remap=tags=>Array.from(new Set((tags||[]).map(tag=>tag===from?to:tag)));
      snapshot.serverTasks.forEach(task=>{task.tags=remap(task.tags);});
      snapshot.queue.forEach(op=>{if(op.payload.tags)op.payload.tags=remap(op.payload.tags);if(op.type==='category_delete'&&op.client_id===from)op.client_id=to;});
    }
    return;
  }
  snapshot.serverTasks=snapshot.serverTasks.filter(task=>task.client_id!==result.client_id);
  if(result.deleted) snapshot.queue=snapshot.queue.filter(op=>op.client_id!==result.client_id);
  else if(result.task) snapshot.serverTasks.push(result.task);
}
class MemoryStore {
  constructor(seed,categories=DEFAULT_CATEGORIES){this.value=emptyState(seed,categories);}
  async read(){return clone(this.value);}
  async mutate(fn){const next=clone(this.value);fn(next);this.value=next;return clone(next);}
}
class LocalStore {
  constructor(db){this.db=db;this.channel=typeof BroadcastChannel==='function'?new BroadcastChannel('todo-workspace-v1'):null;}
  static async open(seed,categories=DEFAULT_CATEGORIES){
    const db=await new Promise((resolve,reject)=>{const req=indexedDB.open('todo-workspace-v1',1);req.onupgradeneeded=()=>req.result.createObjectStore('workspace');req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);req.onblocked=()=>reject(new Error('Bộ nhớ đang được sử dụng bởi một phiên cũ.'));});
    const store=new LocalStore(db);
    await store.mutate(s=>{if(!s.schema)Object.assign(s,emptyState(seed,categories));else if(!Array.isArray(s.categories))s.categories=clone(categories);},false);
    return store;
  }
  async read(){return new Promise((resolve,reject)=>{const tx=this.db.transaction('workspace','readonly');const req=tx.objectStore('workspace').get('state');req.onsuccess=()=>resolve(req.result||{});req.onerror=()=>reject(req.error);});}
  async mutate(fn,notify=true){return new Promise((resolve,reject)=>{
    const tx=this.db.transaction('workspace','readwrite');const object=tx.objectStore('workspace');const req=object.get('state');let next;
    req.onsuccess=()=>{try{next=req.result||{};fn(next);object.put(next,'state');}catch(error){tx.abort();reject(error);}};
    tx.oncomplete=()=>{if(notify)this.channel?.postMessage('changed');resolve(next);};
    tx.onerror=()=>reject(tx.error||new Error('Không ghi được dữ liệu.'));tx.onabort=()=>reject(tx.error||new Error('Không ghi được dữ liệu.'));
  });}
}
/* SERVER TRANSPORT START */
function createGateway(){
  const request=async(url,options={})=>{
    const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),7000);
    try{
      const response=await fetch(url,{cache:'no-store',credentials:'same-origin',...options,signal:controller.signal});
      let data;try{data=await response.json();}catch(_){data=null;}
      if(!response.ok){
        const fallback=response.status===401||response.status===403?'Máy chủ từ chối quyền truy cập.':response.status===404?'Máy chủ chưa có API đồng bộ. Cần triển khai đúng phiên bản ứng dụng.':'Máy chủ chưa sẵn sàng. Thay đổi vẫn được lưu trên thiết bị.';
        const error=new Error(data?.error||fallback);error.permanent=response.status>=400&&response.status<500;throw error;
      }
      if(!data||typeof data!=='object')throw new Error('Máy chủ trả dữ liệu không tương thích. Cần kiểm tra phiên bản triển khai.');
      return data;
    }finally{clearTimeout(timer);}
  };
  return {probe:async()=>{const data=await request('/health');if(data.status!=='ok')throw new Error('Cơ sở dữ liệu chưa sẵn sàng.');},read:()=>request('/api/tasks'),push:op=>request('/api/operations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({op_id:op.op_id,type:op.type,client_id:op.client_id,payload:op.payload})})};
}
/* SERVER TRANSPORT END */
function createDemoGateway(seed,initialCategories=DEFAULT_CATEGORIES){
  let categories=clone(initialCategories),tasks=clone(seed),online=true,counter=Math.max(0,...seed.map(t=>t.id))+1;
  const journal=new Map(),deleted=new Set(),deletedCategories=new Set();
  const wait=()=>new Promise(resolve=>setTimeout(resolve,140));
  const check=()=>{if(!online)throw new Error('Kết nối mẫu đang tắt.');};
  return {setOnline:value=>{online=value;},isOnline:()=>online,restore:(seed,cats=DEFAULT_CATEGORIES)=>{categories=clone(cats);tasks=clone(seed);counter=Math.max(0,...tasks.map(t=>t.id))+1;journal.clear();deleted.clear();deletedCategories.clear();},
    probe:async()=>{await wait();check();},read:async()=>{await wait();check();return{tasks:clone(tasks),categories:clone(categories),deletedCategories:Array.from(deletedCategories)};},
    push:async op=>{await wait();check();if(journal.has(op.op_id))return clone(journal.get(op.op_id));
      let task=tasks.find(t=>t.client_id===op.client_id);const result={op_id:op.op_id,client_id:op.client_id,deleted:false};
      if(op.type==='category_create'){
        let category=categories.find(c=>categoryNameKey(c.name)===categoryNameKey(op.payload.name));
        if(!category){category={id:op.client_id,...clone(op.payload)};categories.push(category);}
        result.category=clone(category);
      }else if(op.type==='category_delete'){categories=categories.filter(c=>c.id!==op.client_id);deletedCategories.add(op.client_id);tasks.forEach(t=>{t.tags=(t.tags||[]).filter(tag=>tag!==op.client_id);});result.category_deleted=true;
      }else if(op.type==='delete'){tasks=tasks.filter(t=>t.client_id!==op.client_id);deleted.add(op.client_id);result.deleted=true;}
      else if(deleted.has(op.client_id)){result.deleted=true;}
      else{
        if(op.type==='create'&&!task){task={...clone(op.payload),id:counter++,client_id:op.client_id,updated_at:new Date().toISOString()};tasks.push(task);}
        else if(op.type==='update'&&task){Object.assign(task,clone(op.payload),{updated_at:new Date().toISOString()});}
        if(task)result.task=clone(task);else result.deleted=true;
      }
      journal.set(op.op_id,clone(result));return result;
    }};
}
const Logic={DEFAULT_CATEGORIES,projectCategories,categoryNameKey,connectionStatus,project,visibleTasks,upcomingGroups,acknowledge,emptyState,dateKey,plusDays,monday,normalize,MemoryStore,createDemoGateway};
if(typeof module!=='undefined'&&module.exports)module.exports=Logic;
if(typeof document==='undefined')return;
const byId=id=>document.getElementById(id),root=byId('todo-clean');if(!root)return;
const bootstrap=JSON.parse(byId('clean-bootstrap').textContent),localPreview=root.dataset.mode==='local';
const themeButton=byId('theme-toggle'),title=byId('title'),search=byId('search'),sort=byId('sort'),dialog=byId('delete-dialog');
const state={health:'unknown',syncing:false,storageError:false,message:''};
let snapshot=emptyState(bootstrap.tasks,bootstrap.categories||DEFAULT_CATEGORIES),store,gateway,syncPromise=null,timer=null,pendingDelete=null;
const owner=uuid();
const announce=text=>{byId('announcement').textContent=text;};
const el=(tag,cls,text)=>{const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=text;return node;};
const icon=name=>{const svg=document.createElementNS('http://www.w3.org/2000/svg','svg'),use=document.createElementNS('http://www.w3.org/2000/svg','use');svg.setAttribute('aria-hidden','true');use.setAttribute('href','#icon-'+name);svg.append(use);return svg;};
function applyTheme(theme){
 document.documentElement.dataset.theme=theme;const dark=theme==='dark';
 byId('theme-icon').setAttribute('href',dark?'#icon-sun':'#icon-moon');
 themeButton.setAttribute('aria-label',dark?'Chuyển sang giao diện sáng':'Chuyển sang giao diện tối');themeButton.setAttribute('aria-pressed',String(dark));
}
let theme='light';try{if(localStorage.getItem('todo-clean-theme')==='dark')theme='dark';}catch(_){}
applyTheme(theme);themeButton.hidden=false;
themeButton.addEventListener('click',()=>{const next=document.documentElement.dataset.theme==='dark'?'light':'dark';applyTheme(next);try{localStorage.setItem('todo-clean-theme',next);}catch(_){}});
function status(){
 const pending=snapshot.queue.length,connection=connectionStatus(state,pending);
 byId('sync-status').textContent=localPreview?(state.storageError?'Chưa lưu được trên thiết bị':'Bản xem thử · Lưu trên thiết bị'):connection.text+(pending&&!state.syncing?` · ${pending} thay đổi chờ gửi`:'');
 byId('sync-dot').dataset.state=state.storageError?'error':localPreview?'online':connection.status;
 byId('sync-message').hidden=!state.message;byId('sync-message').textContent=state.message;
 byId('sync-now').disabled=state.syncing;byId('sync-now').textContent=state.syncing?'Đang đồng bộ…':'Đồng bộ lại';byId('sync-now').hidden=localPreview;
}
function updateInput(){
 byId('character-count').hidden=false;byId('character-count').textContent=`${title.value.length} / 200`;
 byId('add-button').disabled=!title.value.trim()||title.value.length>200;
 byId('add-error').hidden=true;title.removeAttribute('aria-invalid');
}
function render(){
 const tasks=project(snapshot),visible=visibleTasks(tasks,'all',null,search.value,sort.value),list=byId('task-list');
 const focused=document.activeElement?.closest?.('.task')?.dataset.key;
 list.replaceChildren();
 for(const task of visible){
  const row=el('li','task');row.dataset.key=task.client_id;row.dataset.id=String(task.id||'');
  const dot=el('span','task-marker');dot.setAttribute('aria-hidden','true');
  const content=el('span','task-content');content.append(el('span','task-title',task.title));
  if(task.pending)content.append(el('span','task-pending','Chờ đồng bộ'));
  const form=el('form','delete-form');form.method='post';form.action=task.id?`/delete/${task.id}`:'/';
  const button=el('button','icon-button delete-button');button.type='submit';button.setAttribute('aria-label',`Xoá công việc: ${task.title}`);button.title='Xoá công việc';button.append(icon('trash'));form.append(button);row.append(dot,content,form);list.append(row);
 }
 if(!tasks.length){
  const empty=el('li','empty-state'),mark=el('span','empty-icon');mark.setAttribute('aria-hidden','true');mark.append(icon('list'));
  const link=el('a','text-link','Thêm công việc đầu tiên ↗');link.href='#title';
  empty.append(mark,el('h3','','Chưa có công việc nào'),el('p','','Bắt đầu bằng một việc nhỏ bạn muốn làm.'),link);list.append(empty);
 }
 byId('no-results').hidden=!tasks.length||visible.length>0;
 byId('toolbar').hidden=!tasks.length;byId('keyboard-hint').hidden=!tasks.length;
 document.querySelector('.count-badge').textContent=String(tasks.length);
 byId('result-count').textContent=search.value.trim()?`${visible.length} / ${tasks.length} công việc`:`${tasks.length} công việc trong danh sách`;
 byId('search-clear').hidden=!search.value;
 if(focused)Array.from(list.querySelectorAll('.task')).find(row=>row.dataset.key===focused)?.querySelector('button')?.focus();
 status();
}
const adopt=next=>{snapshot=next;render();};
function schedule(delay=0){clearTimeout(timer);timer=setTimeout(synchronize,delay);}
async function commit(type,client_id,payload={}){
 try{
  adopt(await store.mutate(s=>s.queue.push({op_id:uuid(),type,client_id,payload:clone(payload),created_at:new Date().toISOString()})));
  state.storageError=false;state.message='';status();schedule(150);return true;
 }catch(_){state.storageError=true;state.message='Chưa lưu được thay đổi. Hãy giữ trang đang mở và kiểm tra bộ nhớ trình duyệt.';status();return false;}
}
async function synchronize(){
 if(syncPromise)return syncPromise;
 syncPromise=(async()=>{
  let held=false;state.syncing=true;status();
  try{
   const lease=await store.mutate(s=>{if(!s.lease||s.lease.expires<Date.now()||s.lease.owner===owner){s.lease={owner,expires:Date.now()+30000};held=true;}},false);
   if(!held){snapshot=lease;state.health='waiting';render();return;}
   if(!localPreview&&navigator.onLine===false)throw new Error('Ngoại tuyến');
   await gateway.probe();
   const renew=async()=>{let ok=false;await store.mutate(s=>{if(s.lease?.owner===owner){s.lease.expires=Date.now()+30000;ok=true;}},false);if(!ok)throw new Error('Thẻ khác đang đồng bộ.');};
   const refresh=async()=>{
    await renew();const remote=await gateway.read();
    if(!Array.isArray(remote.tasks)||!Array.isArray(remote.categories)||remote.tasks.some(t=>typeof t.client_id!=='string'))throw new Error('Máy chủ trả dữ liệu không tương thích.');
    adopt(await store.mutate(s=>{if(s.lease?.owner===owner){s.serverTasks=remote.tasks;s.categories=remote.categories;s.deletedCategories=remote.deletedCategories||[];}}));
   };
   await refresh();
   for(let i=0;i<100;i++){
    const current=await store.read(),operation=current.queue[0];if(!operation)break;
    await renew();const result=await gateway.push(operation);
    if(result.op_id!==operation.op_id||result.client_id!==operation.client_id)throw new Error('Phản hồi đồng bộ không hợp lệ.');
    adopt(await store.mutate(s=>{if(s.lease?.owner===owner)acknowledge(s,operation.op_id,result);}));if(result.notice)announce(result.notice);
   }
   await refresh();
   adopt(await store.mutate(s=>{if(s.lease?.owner===owner&&!s.queue.length)s.lastSynced=new Date().toISOString();}));
   state.health='online';state.message='';state.storageError=false;
  }catch(error){
   if(error.permanent){state.health='error';state.message=error.message;}
   else if(!localPreview&&navigator.onLine===false){state.health='offline';state.message='Bạn vẫn có thể thêm, tìm kiếm, sắp xếp và xoá công việc. Thay đổi sẽ được gửi khi kết nối trở lại.';}
   else{state.health='unavailable';state.message=error.name==='AbortError'?'Máy chủ phản hồi chậm. Thay đổi vẫn được giữ trên thiết bị.':error instanceof TypeError?'Không kết nối được máy chủ. Thay đổi vẫn được giữ trên thiết bị.':error.message;}
  }finally{
   if(held)try{await store.mutate(s=>{if(s.lease?.owner===owner)s.lease=null;},false);}catch(_){state.storageError=true;}
   state.syncing=false;status();
  }
 })().finally(()=>{syncPromise=null;if(state.health==='online'&&snapshot.queue.length&&!state.message)schedule(300);});
 return syncPromise;
}
async function initialize(){
 try{store=await LocalStore.open(bootstrap.tasks,bootstrap.categories||DEFAULT_CATEGORIES);snapshot=await store.read();if(snapshot.schema!==1)throw new Error('Unknown storage schema');}
 catch(_){state.storageError=true;state.message='Không mở được bộ nhớ ngoại tuyến. Form thêm và xoá vẫn dùng được khi có kết nối máy chủ.';status();return;}
 gateway=localPreview?createDemoGateway(snapshot.serverTasks,snapshot.categories||DEFAULT_CATEGORIES):createGateway();
 const clear=el('button','icon-button search-clear');clear.id='search-clear';clear.type='button';clear.setAttribute('aria-label','Xoá từ khoá tìm kiếm');clear.append(icon('close'));document.querySelector('.search-field').insertBefore(clear,document.querySelector('.search-field kbd'));
 clear.addEventListener('click',()=>{search.value='';render();search.focus();});
 const keyboard=document.querySelector('.search-field kbd');keyboard.addEventListener('click',()=>search.focus());
 title.addEventListener('input',updateInput);updateInput();render();
 byId('add-form').addEventListener('submit',async event=>{
  event.preventDefault();const value=title.value.trim();if(!value||title.value.length>200){byId('add-error').textContent='Nhập tên công việc từ 1 đến 200 ký tự.';byId('add-error').hidden=false;title.setAttribute('aria-invalid','true');title.focus();return;}
  byId('add-button').disabled=true;if(await commit('create',uuid(),{title:value})){title.value='';search.value='';render();announce('Đã lưu công việc trên thiết bị.');title.focus();}updateInput();
 });
 search.addEventListener('input',render);search.addEventListener('search',render);sort.addEventListener('change',render);
 byId('clear-search').addEventListener('click',()=>{search.value='';render();search.focus();});
 byId('task-list').addEventListener('submit',event=>{
  const form=event.target;if(!form.matches('.delete-form'))return;event.preventDefault();
  const key=form.closest('.task').dataset.key,task=project(snapshot).find(t=>t.client_id===key);if(!task)return;
  pendingDelete=key;byId('delete-title').textContent=task.title;dialog.returnValue='';dialog.showModal();
 });
 const cancel=()=>{dialog.close();};
 dialog.querySelectorAll('[value=cancel]').forEach(button=>button.addEventListener('click',event=>{event.preventDefault();cancel();}));
 dialog.addEventListener('cancel',()=>{dialog.returnValue='cancel';});
 dialog.addEventListener('close',()=>{const key=pendingDelete;pendingDelete=null;Array.from(byId('task-list').querySelectorAll('.task')).find(row=>row.dataset.key===key)?.querySelector('button')?.focus();});
 dialog.querySelector('[value=delete]').addEventListener('click',async event=>{
  event.preventDefault();if(!pendingDelete)return;const key=pendingDelete,button=event.currentTarget;button.disabled=true;
  if(await commit('delete',key)){dialog.close();announce('Đã lưu thao tác xoá trên thiết bị.');title.focus();}button.disabled=false;
 });
 byId('sync-now').addEventListener('click',()=>schedule());
 document.addEventListener('keydown',event=>{if(event.key==='/'&&!event.ctrlKey&&!event.metaKey&&!event.altKey&&!event.target.closest?.('input,textarea,select,[contenteditable]')&&!dialog.open&&project(snapshot).length){event.preventDefault();search.focus();}});
 if(store.channel)store.channel.onmessage=async()=>{adopt(await store.read());if(!document.hidden)schedule(500);};
 window.addEventListener('online',()=>schedule());window.addEventListener('offline',()=>{if(!localPreview){state.health='offline';status();}});
 window.addEventListener('focus',()=>schedule());
 document.addEventListener('visibilitychange',async()=>{if(!document.hidden){adopt(await store.read());schedule();}});
 setInterval(()=>{if(!document.hidden)schedule();},25000);
 if(!localPreview&&'serviceWorker' in navigator&&global.isSecureContext)navigator.serviceWorker.register('/service-worker.js?v='+encodeURIComponent(bootstrap.version)).catch(()=>{state.message='Đã lưu dữ liệu, nhưng chưa lưu được trang để tải lại khi mất mạng.';status();});
 root.dispatchEvent(new CustomEvent('clean:ready'));schedule(200);
}
initialize().catch(error=>{state.storageError=true;state.message='Chưa khởi tạo được chế độ ngoại tuyến. Các form cơ bản vẫn hoạt động khi máy chủ sẵn sàng.';status();console.error(error);});
})(globalThis);
