const assert=require('node:assert/strict');
const {connectionStatus,project,visibleTasks,upcomingGroups,acknowledge,emptyState,plusDays,monday,normalize,createDemoGateway}=require('../app/static/app.js');
// A reachable HTTP server is not proof that the task/database API synchronized.
assert.equal(connectionStatus({health:'online',syncing:false},0).status,'online');
for(const health of ['unknown','error','unavailable','waiting','offline']){
 assert.notEqual(connectionStatus({health,syncing:false},0).status,'online',health+' must not show green');
 assert.ok(!connectionStatus({health,syncing:false},0).text.includes('Đã đồng bộ'));
}
assert.notEqual(connectionStatus({health:'online',syncing:true},0).status,'online');
assert.notEqual(connectionStatus({health:'online',syncing:false},2).status,'online');
assert.notEqual(connectionStatus({health:'online',syncing:false,storageError:true},0).status,'online');
const task={id:12,client_id:'00000000-0000-4000-8000-000000000012',title:'Học DevOps',due_date:'2026-10-27',due_time:'14:00',priority:2,tags:['devops'],completed:false};
const s=emptyState([task]);
s.queue.push({op_id:'a',type:'create',client_id:'new',payload:{title:'Việc ngoại tuyến',due_date:'2026-10-28',priority:1,tags:[],completed:false},created_at:'2026-10-27T00:00:00Z'});
s.queue.push({op_id:'b',type:'update',client_id:task.client_id,payload:{completed:true}});
assert.equal(project(s).length,2);assert.equal(project(s)[0].completed,true);assert.equal(project(s)[1].pending,true);
s.queue.push({op_id:'c',type:'delete',client_id:'new',payload:{}});assert.equal(project(s).length,1);
assert.equal(normalize('ĐẶNG HỌC'),'dang hoc');assert.equal(plusDays('2026-12-31',1),'2027-01-01');assert.equal(monday('2026-11-01'),'2026-10-26');
assert.equal(visibleTasks([task],'today',null,'hoc','due','2026-10-27').length,1);
assert.equal(visibleTasks([task],'upcoming',null,'','due','2026-10-26').length,1);
assert.equal(visibleTasks([task],'calendar','2026-10-28','','due','2026-10-27').length,0);
// Date buckets must stay disjoint across Fridays, weekends, and year boundaries.
for(const day of ['2026-10-27','2026-10-30','2026-10-31','2026-11-01','2026-12-31']){
 const scheduled=Array.from({length:15},(_,i)=>({...task,id:i+1,due_date:plusDays(day,i)}));
 const groups=upcomingGroups(scheduled,day),flattened=groups.flatMap(g=>g.tasks);
 assert.equal(flattened.length,scheduled.length);
 assert.equal(new Set(flattened.map(t=>t.id)).size,scheduled.length,'no task appears twice');
 for(const group of groups)assert.ok(group.date>=day,'group add defaults to a future/current date');
 assert.equal(groups[0].tasks[0].due_date,day);
 assert.equal(groups[1].tasks[0].due_date,plusDays(day,1));
}
assert.equal(visibleTasks([task],'upcoming',null,'','due','2026-10-27').length,1,'upcoming includes today');
assert.equal(visibleTasks([task],'all',null,'','newest','2026-10-27','devops').length,1);
assert.equal(visibleTasks([task],'all',null,'','newest','2026-10-27','ca-nhan').length,0);
acknowledge(s,'b',{client_id:task.client_id,task:{...task,completed:true}});assert.equal(s.queue.length,2);
acknowledge(s,'b',{client_id:task.client_id,task:{...task,completed:false}});assert.equal(s.serverTasks[0].completed,true,'stale duplicate ack must not overwrite a later state');
(async()=>{
 const api=createDemoGateway([task]);const op={op_id:'once',type:'create',client_id:'new',payload:{...task,title:'offline'}};
 api.setOnline(false);await assert.rejects(()=>api.push(op));api.setOnline(true);
 const first=await api.push(op),again=await api.push(op);assert.deepEqual(first,again);assert.equal((await api.read()).tasks.length,2);
 await api.push({op_id:'del',type:'delete',client_id:'new',payload:{}});
 const stale=await api.push({...op,op_id:'stale'});assert.equal(stale.deleted,true);assert.equal((await api.read()).tasks.length,1);
 console.log('PASS: offline projection, metadata, completion, deletion, Vietnamese search, calendar boundaries, date views, duplicate ack guard, replay-safe create, tombstone.');
})().catch(error=>{console.error(error);process.exitCode=1;});
