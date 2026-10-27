(function(global) {
'use strict';
const clone = value => JSON.parse(JSON.stringify(value));
const TAG_NAMES = {'hoc-tap':'Học tập',devops:'DevOps','ca-nhan':'Cá nhân'};
const PRIORITIES = {1:'Cao',2:'Trung bình',3:'Thấp'};
const dateKey = value => {const d=new Date(value);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};
const parseDay = value => new Date(`${value}T12:00:00`);
const plusDays = (value,n) => {const d=parseDay(value);d.setDate(d.getDate()+n);return dateKey(d);};
const todayKey = () => dateKey(new Date());
const monday = value => {const d=parseDay(value);return plusDays(value,-((d.getDay()+6)%7));};
const normalize = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[đĐ]/g,'d').toLocaleLowerCase('vi');
const uuid = () => {const b=new Uint8Array(16);global.crypto.getRandomValues(b);b[6]=(b[6]&15)|64;b[8]=(b[8]&63)|128;const s=Array.from(b,x=>x.toString(16).padStart(2,'0')).join('');return `${s.slice(0,8)}-${s.slice(8,12)}-${s.slice(12,16)}-${s.slice(16,20)}-${s.slice(20)}`;};
const emptyState = tasks => ({schema:1,serverTasks:clone(tasks),queue:[],lastSynced:null,lease:null});
function project(snapshot) {
  const map=new Map(snapshot.serverTasks.map(task=>[task.client_id,{...clone(task),pending:false}]));
  for(const op of snapshot.queue) {
    const old=map.get(op.client_id);
    if(op.type==='create') map.set(op.client_id,{id:null,client_id:op.client_id,due_date:null,due_time:null,priority:0,tags:[],completed:false,local_order:op.created_at,...old,...clone(op.payload),pending:true});
    else if(op.type==='update'&&old) map.set(op.client_id,{...old,...clone(op.payload),pending:true});
    else if(op.type==='delete') map.delete(op.client_id);
  }
  return Array.from(map.values());
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
  snapshot.serverTasks=snapshot.serverTasks.filter(task=>task.client_id!==result.client_id);
  if(result.deleted) snapshot.queue=snapshot.queue.filter(op=>op.client_id!==result.client_id);
  else if(result.task) snapshot.serverTasks.push(result.task);
}
class MemoryStore {
  constructor(seed){this.value=emptyState(seed);}
  async read(){return clone(this.value);}
  async mutate(fn){const next=clone(this.value);fn(next);this.value=next;return clone(next);}
}
class LocalStore {
  constructor(db){this.db=db;this.channel=typeof BroadcastChannel==='function'?new BroadcastChannel('todo-workspace-v1'):null;}
  static async open(seed){
    const db=await new Promise((resolve,reject)=>{const req=indexedDB.open('todo-workspace-v1',1);req.onupgradeneeded=()=>req.result.createObjectStore('workspace');req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);req.onblocked=()=>reject(new Error('Bộ nhớ đang được sử dụng bởi một phiên cũ.'));});
    const store=new LocalStore(db);
    await store.mutate(s=>{if(!s.schema)Object.assign(s,emptyState(seed));},false);
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
function createDemoGateway(seed){
  let tasks=clone(seed),online=true,counter=Math.max(0,...seed.map(t=>t.id))+1;
  const journal=new Map(),deleted=new Set();
  const wait=()=>new Promise(resolve=>setTimeout(resolve,140));
  const check=()=>{if(!online)throw new Error('Kết nối mẫu đang tắt.');};
  return {setOnline:value=>{online=value;},isOnline:()=>online,restore:seed=>{tasks=clone(seed);counter=Math.max(0,...tasks.map(t=>t.id))+1;journal.clear();deleted.clear();},
    probe:async()=>{await wait();check();},read:async()=>{await wait();check();return{tasks:clone(tasks)};},
    push:async op=>{await wait();check();if(journal.has(op.op_id))return clone(journal.get(op.op_id));
      let task=tasks.find(t=>t.client_id===op.client_id);const result={op_id:op.op_id,client_id:op.client_id,deleted:false};
      if(op.type==='delete'){tasks=tasks.filter(t=>t.client_id!==op.client_id);deleted.add(op.client_id);result.deleted=true;}
      else if(deleted.has(op.client_id)){result.deleted=true;}
      else{
        if(op.type==='create'&&!task){task={...clone(op.payload),id:counter++,client_id:op.client_id,updated_at:new Date().toISOString()};tasks.push(task);}
        else if(op.type==='update'&&task){Object.assign(task,clone(op.payload),{updated_at:new Date().toISOString()});}
        if(task)result.task=clone(task);else result.deleted=true;
      }
      journal.set(op.op_id,clone(result));return result;
    }};
}
const Logic={connectionStatus,project,visibleTasks,upcomingGroups,acknowledge,emptyState,dateKey,plusDays,monday,normalize,MemoryStore,createDemoGateway};
if(typeof module!=='undefined'&&module.exports)module.exports=Logic;
if(typeof document==='undefined')return;
const root=document.getElementById('todo-workspace');if(!root)return;
const q=selector=>root.querySelector(selector);
const qa=selector=>Array.from(root.querySelectorAll(selector));
const preview=root.dataset.mode==='preview';
const bootstrap=JSON.parse(q('#ow-bootstrap').textContent);
if(preview&&bootstrap.demoBaseDate){const delta=Math.round((parseDay(todayKey())-parseDay(bootstrap.demoBaseDate))/86400000);bootstrap.tasks.forEach(task=>{if(task.due_date)task.due_date=plusDays(task.due_date,delta);});}
const state={view:'upcoming',tag:null,editKey:null,date:null,week:monday(todayKey()),month:todayKey().slice(0,7),query:'',sort:'newest',health:'unknown',syncing:false,storageError:false,message:'',capability:''};
let store,snapshot=emptyState(bootstrap.tasks),all=project(snapshot),pendingDelete=null,syncPromise=null,syncTimer=null;
const owner=uuid();
const gateway=preview?createDemoGateway(bootstrap.tasks):createGateway();
const announce=text=>{q('[data-announcement]').textContent=text;};
const publish=()=>root.dispatchEvent(new CustomEvent('workspace:change'));
const el=(tag,cls,text)=>{const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=text;return node;};
const shortDate=value=>parseDay(value).toLocaleDateString('vi-VN',{day:'numeric',month:'numeric'});
const dueLabel=task=>{if(!task.due_date)return '';const today=todayKey();let text=task.due_date===today?'Hôm nay':task.due_date===plusDays(today,1)?'Ngày mai':shortDate(task.due_date);if(task.due_time)text+=` · ${task.due_time}`;return text;};
const overdue=task=>!task.completed&&task.due_date&&(task.due_date<todayKey()||(task.due_date===todayKey()&&task.due_time&&task.due_time<new Date().toTimeString().slice(0,5)));
function applyTheme(theme){
  const dark=theme==='dark';root.dataset.theme=dark?'dark':'light';
  q('[data-theme-toggle]').setAttribute('aria-pressed',String(dark));
  q('[data-theme-label]').textContent=dark?'Chuyển sang sáng':'Chuyển sang tối';
}
const settings=q('[data-settings-dialog]');
function openSettings(){if(!settings.open)settings.showModal();}
qa('[data-open-settings]').forEach(button=>{button.hidden=false;button.addEventListener('click',openSettings);});
qa('[data-settings-close]').forEach(button=>button.addEventListener('click',()=>settings.close()));
settings.addEventListener('click',event=>{if(event.target===settings){const rect=settings.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)settings.close();}});
let savedTheme=null;try{savedTheme=localStorage.getItem('todo-workspace-theme');}catch(_){}
applyTheme(savedTheme||((typeof matchMedia==='function'&&matchMedia('(prefers-color-scheme: dark)').matches)?'dark':'light'));
q('[data-theme-toggle]').addEventListener('click',()=>{applyTheme(root.dataset.theme==='dark'?'light':'dark');try{localStorage.setItem('todo-workspace-theme',root.dataset.theme);}catch(_){}publish();});

function renderTask(task){
  const node=q('[data-task-template]').content.firstElementChild.cloneNode(true);
  node.dataset.key=task.client_id;node.classList.toggle('is-completed',Boolean(task.completed));
  node.querySelector('[data-task-id]').textContent=task.id?`#${task.id}`:'#Tạm';
  node.querySelector('[data-task-title]').textContent=task.title;node.querySelector('[data-edit]').hidden=false;node.querySelector('[data-edit]').setAttribute('aria-label',`Sửa công việc: ${task.title}`);
  const complete=node.querySelector('[data-complete-form]');complete.action=task.id?`/complete/${task.id}`:'#';complete.querySelector('input').value=String(!task.completed);
  const check=node.querySelector('[data-check]');check.setAttribute('aria-checked',String(task.completed));check.setAttribute('aria-label',`${task.completed?'Đánh dấu chưa hoàn thành':'Đánh dấu hoàn thành'}: ${task.title}`);
  const del=node.querySelector('[data-delete-form]');del.action=task.id?`/delete/${task.id}`:'#';node.querySelector('[data-delete]').setAttribute('aria-label',`Xoá công việc: ${task.title}`);
  const badges=node.querySelector('[data-badges]');badges.replaceChildren();
  if(task.due_date){const due=el('span','ow-pill'+(overdue(task)?' is-overdue':''),dueLabel(task));due.setAttribute('aria-label',(overdue(task)?'Quá hạn: ':'Lịch thực hiện: ')+dueLabel(task));badges.append(due);}
  for(const tag of task.tags||[])if(TAG_NAMES[tag])badges.append(el('span',`ow-tag tag-${tag}`,TAG_NAMES[tag]));
  if(task.priority)badges.append(el('span',`ow-priority p${task.priority}`,PRIORITIES[task.priority]));
  if(task.pending)badges.append(el('span','ow-pending','⏳ Chờ đồng bộ'));
  badges.hidden=!badges.children.length;
  return node;
}
function calendar(container){
  container.replaceChildren();const anchor=parseDay(state.month+'-01');
  const header=el('div','ow-calendar-header');header.append(el('strong','',anchor.toLocaleDateString('vi-VN',{month:'long',year:'numeric'})));
  const nav=el('div');for(const [delta,label,text] of [[-1,'Tháng trước','‹'],[1,'Tháng sau','›']]){const button=el('button','ow-small-button',text);button.type='button';button.dataset.monthNav=delta;button.setAttribute('aria-label',label);nav.append(button);}header.append(nav);container.append(header);
  const names=el('div','ow-calendar-weekdays');for(const name of ['T2','T3','T4','T5','T6','T7','CN'])names.append(el('span','',name));container.append(names);
  const grid=el('div','ow-calendar-days');const first=monday(dateKey(anchor));const busy=new Set(all.filter(t=>!t.completed&&t.due_date).map(t=>t.due_date));
  for(let i=0;i<42;i++){
    const day=plusDays(first,i),d=parseDay(day),button=el('button','ow-calendar-day');button.type='button';button.dataset.day=day;
    button.classList.toggle('is-outside',day.slice(0,7)!==state.month);button.classList.toggle('is-today',day===todayKey());button.classList.toggle('is-selected',(state.view==='calendar'?state.date:null)===day);button.classList.toggle('has-tasks',busy.has(day));
    button.setAttribute('aria-label',d.toLocaleDateString('vi-VN',{weekday:'long',day:'numeric',month:'long',year:'numeric'})+(busy.has(day)?', có công việc':''));button.setAttribute('aria-pressed',String(state.view==='calendar'&&state.date===day));button.append(el('span','',String(d.getDate())),el('span','ow-day-dot'));grid.append(button);
  }container.append(grid);
}
function renderWeek(){
  const strip=q('[data-week]');strip.replaceChildren();const busy=new Set(all.filter(t=>!t.completed&&t.due_date).map(t=>t.due_date));
  for(let i=0;i<7;i++){const day=plusDays(state.week,i),button=el('button','ow-week-day');button.type='button';button.dataset.day=day;button.classList.toggle('is-today',day===todayKey());button.classList.toggle('is-selected',(state.view==='calendar'&&state.date===day)||(state.view==='today'&&day===todayKey()));button.classList.toggle('has-tasks',busy.has(day));button.setAttribute('aria-label',parseDay(day).toLocaleDateString('vi-VN',{weekday:'long',day:'numeric',month:'long'})+(busy.has(day)?', có công việc':''));button.setAttribute('aria-pressed',String(button.classList.contains('is-selected')));button.append(el('span','day-name',['Thứ 2','Thứ 3','Thứ 4','Thứ 5','Thứ 6','Thứ 7','CN'][i]),el('span','day-number',String(parseDay(day).getDate())),el('span','ow-day-dot'));strip.append(button);}
  q('[data-week-label]').textContent=`${shortDate(state.week)} – ${shortDate(plusDays(state.week,6))}`;
}
function renderStatus(){
  const pending=snapshot.queue.length;
  let {text,status}=connectionStatus(state,pending);
  if(preview)text=text.replace('Trực tuyến','Trực tuyến mẫu').replace('Chế độ ngoại tuyến','Ngoại tuyến mẫu');
  q('[data-status]').textContent=text;q('[data-status-dot]').dataset.state=status;
  q('[data-queue-count]').textContent=String(pending);
  q('[data-stored-count]').textContent=`${all.length} việc đang lưu`;
  q('[data-sync-detail]').textContent=state.health==='offline'||state.health==='unavailable'?'Thay đổi được giữ trong trình duyệt và tự gửi lại khi kết nối sẵn sàng.':state.health==='error'?'Chưa xác nhận dữ liệu trên máy chủ. Các thay đổi đang chờ vẫn được giữ trên thiết bị.':pending?'Có thay đổi trên thiết bị chưa được máy chủ xác nhận.':state.health==='online'?'Danh sách đã được đối chiếu với dữ liệu PostgreSQL trên máy chủ.':'Ứng dụng sẽ kiểm tra máy chủ và cơ sở dữ liệu trước khi xác nhận đồng bộ.';
  q('[data-sync-error]').hidden=!state.message;q('[data-sync-error]').textContent=state.message;
  q('[data-last-sync]').textContent=snapshot.lastSynced?new Date(snapshot.lastSynced).toLocaleString('vi-VN',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}):'Chưa đồng bộ';
  q('[data-sync-label]').textContent=state.syncing?'Đang đồng bộ…':'Đồng bộ ngay';
  q('[data-sync-now]').disabled=state.syncing;
  q('[data-sync-now]').setAttribute('aria-busy',String(state.syncing));
  const banner=q('[data-banner]');const textNode=q('[data-banner-text]');
  banner.hidden=!(state.storageError||state.message||(state.health==='offline'&&pending));
  textNode.textContent=state.storageError?'Không ghi được vào bộ nhớ thiết bị. Thay đổi vừa rồi chưa được lưu.':state.message||(pending?`Đã giữ ${pending} thay đổi trên thiết bị. Ứng dụng sẽ tự gửi khi kết nối trở lại.`:'');
  q('[data-offline-capability]').textContent=preview?'Bản mô phỏng dùng dữ liệu mẫu, không kết nối EC2.':state.capability;
}
function renderGroup(group){
  const section=el('section','ow-task-group');section.dataset.group=group.key;section.setAttribute('aria-label',group.title);
  if(group.key==='later')section.classList.add('is-wide');
  const heading=el('div','ow-group-heading');heading.append(el('h2','',group.title),el('span','ow-group-count',String(group.tasks.length)));section.append(heading);
  const add=el('button','ow-group-add');add.type='button';add.dataset.newDay=group.date||'';add.setAttribute('aria-label',`Thêm công việc · ${group.title}`);add.append(el('span','','+'),el('span','','Thêm công việc'));section.append(add);
  const list=el('ul','ow-task-list');
  if(group.tasks.length)for(const task of group.tasks)list.append(renderTask(task));
  else list.append(el('li','ow-group-empty','Chưa có công việc.'));
  section.append(list);return section;
}
function render(){
  all=project(snapshot);root.dataset.view=state.view;
  const visible=visibleTasks(all,state.view,state.date,state.query,state.sort,todayKey(),state.tag);
  const title=state.query?'Tìm kiếm':state.tag?TAG_NAMES[state.tag]:{all:'Tất cả',today:'Hôm nay',upcoming:'Sắp tới',calendar:'Lịch công việc'}[state.view];
  q('[data-page-title]').textContent=title;q('[data-total]').textContent=String(visible.length);
  q('[data-view-description]').textContent=state.query?`Kết quả cho “${state.query}”`:state.tag?'Những công việc trong cùng một nhóm.':{all:'Mọi công việc, ở cùng một nơi.',today:'Tập trung vào những việc của hôm nay.',upcoming:'Hôm nay, ngày mai và những ngày tiếp theo.',calendar:'Chọn một ngày để xem và sắp xếp công việc.'}[state.view];
  const list=q('[data-list]');list.replaceChildren();list.classList.toggle('is-upcoming',state.view==='upcoming');
  if(!visible.length&&state.query){
    const empty=el('div','ow-empty');empty.append(el('h3','','Không tìm thấy công việc'),el('p','','Thử từ khoá khác hoặc bỏ bộ lọc.'));
    const button=el('button','ow-text-button','Xem tất cả công việc');button.type='button';button.dataset.resetFilters='';empty.append(button);list.append(empty);
  }else{
    const groups=state.view==='upcoming'?upcomingGroups(visible):[{key:'list',title:state.view==='calendar'?`Ngày ${shortDate(state.date||todayKey())}`:state.tag?TAG_NAMES[state.tag]:state.view==='today'?'Công việc hôm nay':'Danh sách công việc',date:state.view==='calendar'?(state.date||todayKey()):state.view==='today'?todayKey():'',tasks:visible}];
    for(const group of groups)list.append(renderGroup(group));
  }
  const done=visible.filter(t=>t.completed).length;
  q('[data-result-count]').textContent=`${visible.length-done} việc cần làm · ${done} đã xong`;
  q('[data-clear-filter]').hidden=!(state.tag||state.query||state.view==='calendar');
  q('[data-clear-search]').hidden=!state.query;q('[data-search-shortcut]').hidden=Boolean(state.query);
  qa('[data-view]').forEach(button=>{const selected=button.dataset.view===state.view&&!state.tag&&!state.query;if(selected)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');});
  qa('[data-nav-count]').forEach(counter=>{counter.textContent=String(visibleTasks(all,counter.dataset.navCount,null,'','newest').length);});
  qa('[data-category]').forEach(button=>button.setAttribute('aria-pressed',String(state.tag===button.dataset.category)));
  qa('[data-category-count]').forEach(counter=>counter.textContent=String(all.filter(t=>(t.tags||[]).includes(counter.dataset.categoryCount)).length));
  q('[data-main-calendar]').hidden=state.view!=='calendar';q('[data-week-section]').hidden=state.view!=='calendar';
  if(state.view==='calendar'){calendar(q('[data-main-calendar]'));renderWeek();}
  const daily=all.filter(t=>t.due_date===todayKey()),dailyDone=daily.filter(t=>t.completed).length,percent=daily.length?Math.round(dailyDone/daily.length*100):0;
  q('[data-progress-ring]').style.setProperty('--progress',`${percent*3.6}deg`);q('[data-progress-ring]').setAttribute('aria-label',`${dailyDone} trên ${daily.length} công việc hôm nay đã hoàn thành`);
  q('[data-daily-progress]').hidden=false;q('[data-progress-value]').textContent=`${percent}%`;q('[data-progress-text]').textContent=daily.length?`${dailyDone} / ${daily.length} việc đã xong`:'Hôm nay chưa có lịch';q('[data-progress-detail]').textContent=daily.length?`${daily.length-dailyDone} việc còn lại trong ngày.`:'Gắn lịch để theo dõi tiến độ.';
  renderStatus();
}
const adopt=next=>{snapshot=next;render();publish();};
async function commit(type,client_id,payload={}){
  const operation={op_id:uuid(),type,client_id,payload:clone(payload),created_at:new Date().toISOString()};
  try{adopt(await store.mutate(s=>s.queue.push(operation)));state.storageError=false;state.message='';renderStatus();scheduleSync(150);return true;}
  catch(_){state.storageError=true;renderStatus();return false;}
}
function scheduleSync(delay=0){clearTimeout(syncTimer);syncTimer=setTimeout(()=>synchronize(),delay);}
async function synchronize(){
  if(syncPromise)return syncPromise;
  syncPromise=(async()=>{
    let held=false;state.syncing=true;renderStatus();
    try{
      const lease=await store.mutate(s=>{if(!s.lease||s.lease.expires<Date.now()||s.lease.owner===owner){s.lease={owner,expires:Date.now()+30000};held=true;}},false);
      if(!held){snapshot=lease;state.health='waiting';render();return;}
      if(!preview&&navigator.onLine===false)throw new Error('Ngoại tuyến');
      await gateway.probe();
      const renew=async()=>{let ok=false;await store.mutate(s=>{if(s.lease?.owner===owner){s.lease.expires=Date.now()+30000;ok=true;}},false);if(!ok)throw new Error('Phiên khác đang đồng bộ.');};
      await renew();const remote=await gateway.read();if(!Array.isArray(remote.tasks)||remote.tasks.some(t=>typeof t.client_id!=='string'))throw new Error('Dữ liệu máy chủ không tương thích.');
      adopt(await store.mutate(s=>{if(s.lease?.owner===owner)s.serverTasks=remote.tasks;}));
      for(let i=0;i<100;i++){
        const current=await store.read();const operation=current.queue[0];if(!operation)break;
        await renew();const result=await gateway.push(operation);if(result.op_id!==operation.op_id||result.client_id!==operation.client_id)throw new Error('Phản hồi đồng bộ không hợp lệ.');
        adopt(await store.mutate(s=>{if(s.lease?.owner===owner)acknowledge(s,operation.op_id,result);}));
        if(result.notice)announce(result.notice);
      }
      await renew();const final=await gateway.read();if(!Array.isArray(final.tasks))throw new Error('Dữ liệu máy chủ không hợp lệ.');
      adopt(await store.mutate(s=>{if(s.lease?.owner===owner){s.serverTasks=final.tasks;if(!s.queue.length)s.lastSynced=new Date().toISOString();}}));
      state.health='online';state.message='';state.storageError=false;
    }catch(error){
      if(error.permanent){state.message=error.message;state.health='error';}
      else if(!preview&&navigator.onLine===false){state.health='offline';state.message='';}
      else{state.health='unavailable';state.message=error.name==='AbortError'?'Máy chủ phản hồi quá chậm. Thay đổi vẫn được giữ trên thiết bị.':error instanceof TypeError?'Không kết nối được máy chủ. Ứng dụng sẽ tự thử lại.':error.message||'Chưa thể xác nhận đồng bộ với máy chủ.';}
    }finally{
      if(held){try{await store.mutate(s=>{if(s.lease?.owner===owner)s.lease=null;},false);}catch(_){state.storageError=true;}}
      state.syncing=false;renderStatus();publish();
    }
  })().finally(()=>{syncPromise=null;if(state.health==='online'&&snapshot.queue.length&&!state.message)scheduleSync(250);});
  return syncPromise;
}

function updateComposer(){
  const input=q('[data-title]'),count=q('[data-counter]');count.textContent=`${input.value.length}/200`;q('[data-add-button]').disabled=!input.value.trim()||input.value.length>200;
  q('[data-input-error]').hidden=true;input.removeAttribute('aria-invalid');
  const due=q('[data-due-date]').value,priority=Number(q('[data-priority]').value),tags=qa('[data-tag]').filter(t=>t.checked);
  q('[data-date-label]').textContent=due?(due===todayKey()?'Hôm nay':shortDate(due)):'Lên lịch';q('[data-priority-label]').textContent=PRIORITIES[priority]||'Ưu tiên';q('[data-priority-label]').className=priority?`p${priority}`:'';q('[data-tags-label]').textContent=tags.length?`${tags.length} thẻ`:'Gắn thẻ';
}
function clearComposer(){state.editKey=null;q('[data-composer-heading]').textContent='Thêm công việc';q('[data-title]').value='';q('[data-due-date]').value='';q('[data-due-time]').value='';q('[data-priority]').value='0';qa('[data-tag]').forEach(tag=>tag.checked=false);q('[data-add-label]').textContent='Thêm';q('[data-cancel-edit]').hidden=true;updateComposer();}
function selectDay(day){state.tag=null;state.date=day;state.view='calendar';state.month=day.slice(0,7);state.week=monday(day);render();publish();}
function resetFilters(){state.view='all';state.tag=null;state.date=null;state.query='';q('[data-search]').value='';render();publish();}
const narrow=()=>root.getBoundingClientRect().width<=780;
function closeMenuOnMobile(){if(narrow())q('[data-sidebar]').open=false;}
function openComposer(day){
  if(state.editKey)clearComposer();
  q('[data-composer]').hidden=false;
  const value=day!==undefined?day:state.view==='upcoming'||state.view==='today'?todayKey():state.view==='calendar'?(state.date||todayKey()):'';
  q('[data-due-date]').value=value;
  if(!value)q('[data-due-time]').value='';
  if(state.tag)qa('[data-tag]').forEach(input=>{input.checked=input.value===state.tag;});
  updateComposer();q('[data-title]').focus();q('[data-composer]').scrollIntoView?.({block:'nearest',behavior:'auto'});
}
async function initialize(){
  try{store=preview?new MemoryStore(bootstrap.tasks):await LocalStore.open(bootstrap.tasks);snapshot=await store.read();if(snapshot.schema!==1)throw new Error('Bộ nhớ có phiên bản không tương thích.');}
  catch(_){q('[data-banner]').hidden=false;q('[data-banner-text]').textContent='Trình duyệt không cho phép lưu dữ liệu ngoại tuyến. Các form cơ bản vẫn hoạt động khi có mạng.';q('[data-status]').textContent='Chưa bật lưu ngoại tuyến';q('[data-sync-detail]').textContent='Các form cơ bản cần kết nối máy chủ. Bộ nhớ ngoại tuyến chưa được bật.';q('[data-sync-now]').disabled=true;return;}
  for(const selector of ['[data-toolbar]','[data-views]','[data-categories]','[data-sort-control]','[data-date-presets]','[data-clear-date]','[data-counter]','[data-new-task]','[data-close-composer]'])q(selector).hidden=false;
  q('[data-composer]').hidden=true;if(narrow())q('[data-sidebar]').open=false;
  render();updateComposer();
  q('[data-new-task]').addEventListener('click',()=>openComposer());
  q('[data-close-composer]').addEventListener('click',()=>{clearComposer();q('[data-composer]').hidden=true;q('[data-new-task]').focus();});
  q('[data-title]').addEventListener('input',updateComposer);q('[data-cancel-edit]').addEventListener('click',()=>{clearComposer();q('[data-composer]').hidden=true;});
  q('[data-due-date]').addEventListener('change',()=>{if(!q('[data-due-date]').value)q('[data-due-time]').value='';updateComposer();});
  q('[data-priority]').addEventListener('change',updateComposer);qa('[data-tag]').forEach(tag=>tag.addEventListener('change',updateComposer));
  q('[data-due-time]').addEventListener('change',()=>{if(q('[data-due-time]').value&&!q('[data-due-date]').value)q('[data-due-date]').value=todayKey();updateComposer();});
  q('[data-add-form]').addEventListener('submit',async event=>{
    event.preventDefault();const input=q('[data-title]'),title=input.value.trim();
    if(!title||input.value.length>200){q('[data-input-error]').textContent='Nhập tên công việc từ 1 đến 200 ký tự.';q('[data-input-error]').hidden=false;input.setAttribute('aria-invalid','true');input.focus();return;}
    const payload={title,due_date:q('[data-due-date]').value||null,due_time:q('[data-due-time]').value||null,priority:Number(q('[data-priority]').value),tags:qa('[data-tag]').filter(t=>t.checked).map(t=>t.value),completed:state.editKey?Boolean(all.find(t=>t.client_id===state.editKey)?.completed):false};
    if(payload.due_time&&!payload.due_date){q('[data-input-error]').textContent='Hãy chọn ngày trước khi đặt giờ.';q('[data-input-error]').hidden=false;return;}
    q('[data-add-button]').disabled=true;
    if(await commit(state.editKey?'update':'create',state.editKey||uuid(),payload)){clearComposer();input.value='';q('[data-due-date]').value='';q('[data-due-time]').value='';q('[data-priority]').value='0';qa('[data-tag]').forEach(tag=>tag.checked=false);qa('[data-command]').forEach(command=>command.open=false);q('[data-composer]').hidden=true;render();announce('Đã lưu công việc trên thiết bị.');q('[data-new-task]').focus();}
    updateComposer();
  });
  const search=q('[data-search]');search.addEventListener('input',()=>{state.query=search.value;if(state.query){state.view='all';state.tag=null;}render();publish();});search.addEventListener('search',()=>{state.query=search.value;if(state.query){state.view='all';state.tag=null;}render();publish();});
  q('[data-clear-search]').addEventListener('click',()=>{state.query='';search.value='';render();search.focus();publish();});
  q('[data-search-shortcut]').addEventListener('click',()=>search.focus());
  q('[data-sort]').addEventListener('change',event=>{state.sort=event.target.value;render();publish();});
  q('[data-clear-filter]').addEventListener('click',resetFilters);
  q('[data-this-week]').addEventListener('click',()=>{state.week=monday(todayKey());renderWeek();});
  root.addEventListener('click',event=>{
    const target=event.target.closest('button');if(!target)return;
    if(target.hasAttribute('data-edit')){const task=all.find(t=>t.client_id===target.closest('[data-task]').dataset.key);if(task){state.editKey=task.client_id;q('[data-composer]').hidden=false;q('[data-composer-heading]').textContent='Sửa công việc';q('[data-title]').value=task.title;q('[data-due-date]').value=task.due_date||'';q('[data-due-time]').value=task.due_time||'';q('[data-priority]').value=String(task.priority);qa('[data-tag]').forEach(t=>t.checked=task.tags.includes(t.value));q('[data-add-label]').textContent='Lưu';q('[data-cancel-edit]').hidden=false;updateComposer();q('[data-title]').focus();q('[data-add-form]').scrollIntoView?.({block:'center'});}}
    if(target.dataset.datePreset){const today=todayKey();const value=target.dataset.datePreset;q('[data-due-date]').value=value==='today'?today:value==='tomorrow'?plusDays(today,1):plusDays(today,(6-parseDay(today).getDay()+7)%7);updateComposer();target.closest('details').open=false;q('[data-title]').focus();}
    if(target.hasAttribute('data-clear-date')){q('[data-due-date]').value='';q('[data-due-time]').value='';updateComposer();target.closest('details').open=false;}
    if(target.hasAttribute('data-new-day'))openComposer(target.dataset.newDay);
    if(target.dataset.category){state.view='all';state.tag=target.dataset.category;state.query='';q('[data-search]').value='';render();closeMenuOnMobile();publish();}
    if(target.dataset.view){state.tag=null;state.query='';q('[data-search]').value='';state.view=target.dataset.view;state.date=state.view==='calendar'?todayKey():null;if(state.view==='today'||state.view==='calendar'){state.week=monday(todayKey());state.month=todayKey().slice(0,7);}render();closeMenuOnMobile();publish();}
    if(target.dataset.day){selectDay(target.dataset.day);}
    if(target.dataset.weekNav){state.week=plusDays(state.week,Number(target.dataset.weekNav)*7);renderWeek();}
    if(target.dataset.monthNav){const anchor=parseDay(state.month+'-01');anchor.setMonth(anchor.getMonth()+Number(target.dataset.monthNav));state.month=dateKey(anchor).slice(0,7);if(state.view==='calendar'){state.date=state.month+'-01';state.week=monday(state.date);}render();publish();}
    if(target.hasAttribute('data-reset-filters'))resetFilters();
  });
  root.addEventListener('submit',async event=>{
    const form=event.target;
    if(form.matches('[data-complete-form]')){event.preventDefault();const key=form.closest('[data-task]').dataset.key,task=all.find(t=>t.client_id===key);if(task&&await commit('update',key,{completed:!task.completed})){announce(task.completed?'Đã chuyển về chưa hoàn thành.':'Đã đánh dấu hoàn thành.');q(`[data-key="${key}"] [data-check]`)?.focus();}}
    else if(form.matches('[data-delete-form]')){event.preventDefault();const key=form.closest('[data-task]').dataset.key,task=all.find(t=>t.client_id===key);if(!task)return;pendingDelete=key;q('[data-delete-preview]').textContent=task.title;const dialog=q('[data-delete-dialog]');dialog.returnValue='';dialog.showModal();}
  });
  q('[data-delete-cancel]').addEventListener('click',()=>{pendingDelete=null;q('[data-delete-dialog]').close();});
  q('[data-delete-confirm]').addEventListener('click',async()=>{if(!pendingDelete)return;const key=pendingDelete;const button=q('[data-delete-confirm]');button.disabled=true;if(await commit('delete',key)){if(state.editKey===key){clearComposer();q('[data-composer]').hidden=true;}pendingDelete=null;q('[data-delete-dialog]').close();announce('Đã lưu thao tác xoá trên thiết bị.');q('[data-new-task]').focus();}button.disabled=false;});
  q('[data-delete-dialog]').addEventListener('cancel',()=>{pendingDelete=null;});
  document.addEventListener('keydown',event=>{if(preview&&event.target!==document.body&&!root.contains(event.target))return;const editing=event.target.closest?.('input,textarea,select,[contenteditable]');if(event.key==='/'&&!editing&&!event.ctrlKey&&!event.metaKey&&!event.altKey&&!q('[data-delete-dialog]').open&&!settings.open){event.preventDefault();q('[data-sidebar]').open=true;search.focus();}if(event.key==='Escape')qa('[data-command]').forEach(command=>command.open=false);});
  document.addEventListener('pointerdown',event=>{if(!root.contains(event.target))return;qa('[data-command]').forEach(command=>{if(!command.contains(event.target))command.open=false;});});
  qa('[data-command]').forEach(command=>command.addEventListener('toggle',()=>{if(command.open)qa('[data-command]').forEach(other=>{if(other!==command)other.open=false;});}));
  q('[data-sync-now]').addEventListener('click',()=>{state.message='';scheduleSync();});
  if(!preview){
    store.channel&&(store.channel.onmessage=async()=>{adopt(await store.read());if(!document.hidden)scheduleSync(500);});
    window.addEventListener('online',()=>scheduleSync());window.addEventListener('offline',()=>{state.health='offline';renderStatus();});
    document.addEventListener('visibilitychange',async()=>{if(!document.hidden){adopt(await store.read());scheduleSync();}});
    setInterval(()=>{if(!document.hidden)scheduleSync();},25000);
    /* SERVICE WORKER REGISTRATION START */
    if('serviceWorker' in navigator&&global.isSecureContext){
      state.capability='IndexedDB giữ dữ liệu trên thiết bị. Đang chuẩn bị bộ nhớ trang.';
      navigator.serviceWorker.register('/service-worker.js?v='+encodeURIComponent(bootstrap.version)).then(()=>navigator.serviceWorker.ready).then(()=>{state.capability='Trang được lưu cho lần mở lại ngoại tuyến sau khi tải thành công.';renderStatus();}).catch(()=>{state.capability='Đã lưu dữ liệu; chưa lưu được trang để mở lại ngoại tuyến.';renderStatus();});
    }else state.capability='Đã lưu dữ liệu. Cần HTTPS hoặc localhost để tải lại trang khi mất mạng.';
    /* SERVICE WORKER REGISTRATION END */
  }
  if(preview){
    state.capability='Bản xem trước mô phỏng máy chủ và hàng đợi.';
    root.workspacePreview={
      toggleNetwork:()=>{gateway.setOnline(!gateway.isOnline());if(!gateway.isOnline())state.health='offline';renderStatus();publish();if(gateway.isOnline())scheduleSync();return gateway.isOnline();},
      getState:()=>({schema:1,snapshot:{...clone(snapshot),lease:null},ui:{view:state.view,tag:state.tag,date:state.date,week:state.week,month:state.month,sort:state.sort,query:state.query,theme:root.dataset.theme},online:gateway.isOnline()}),
      setState:async saved=>{if(saved?.schema!==1||saved.snapshot?.schema!==1||!Array.isArray(saved.snapshot.queue)||!Array.isArray(saved.snapshot.serverTasks))return;gateway.restore(saved.snapshot.serverTasks);await store.mutate(s=>Object.assign(s,clone(saved.snapshot),{lease:null}));Object.assign(state,saved.ui||{});applyTheme(saved.ui?.theme||'light');q('[data-sort]').value=state.sort;q('[data-search]').value=state.query;gateway.setOnline(saved.online!==false);state.health=saved.online===false?'offline':'unknown';snapshot=await store.read();render();},
      sync:synchronize
    };
  }
  root.dispatchEvent(new CustomEvent('workspace:ready'));renderStatus();scheduleSync(200);
}
initialize().catch(error=>{q('[data-banner]').hidden=false;q('[data-banner-text]').textContent='Không khởi tạo được không gian làm việc. Các form cơ bản vẫn có thể dùng khi máy chủ hoạt động.';console.error(error);});
})(globalThis);
