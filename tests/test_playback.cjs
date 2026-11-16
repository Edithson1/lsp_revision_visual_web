const {test}=require('node:test');
const assert=require('node:assert/strict');
const {ComparisonPlayer}=require('../dist/playback.js');

class Video extends EventTarget {
  constructor(ready=4){super();this.readyState=ready;this.duration=2;this._time=0;this.paused=true;this.seeking=false;this.seeks=0;this.starts=0;this.playbackRate=1;}
  getAttribute(name){return name==='src'?'test.mp4':null;}
  get currentTime(){return this._time;}
  set currentTime(value){this._time=value;this.seeks++;this.seeking=true;queueMicrotask(()=>{this.seeking=false;this.dispatchEvent(new Event('seeked'));});}
  pause(){this.paused=true;}
  play(){this.paused=false;this.starts++;return Promise.resolve();}
}
function setup(t,ready=4,options={}) {
  const videos=[new Video(),new Video(ready)];
  const errors=[];
  const player=new ComparisonPlayer(videos,{onError:e=>errors.push(e),...options});
  player.configure([{fps:30,frames:60},{fps:30,frames:60}]);
  t.after(()=>{player.stop();clearInterval(player.timer);});
  return {player,videos,errors};
}
test('el arranque espera ambos videos y los inicia en la misma posición',async t=>{
  const {player,videos}=setup(t,0);
  const pending=player.play();
  await Promise.resolve();
  assert.deepEqual(videos.map(v=>v.starts),[0,0]);
  videos[1].readyState=4;videos[1].dispatchEvent(new Event('canplay'));
  await pending;
  assert.deepEqual(videos.map(v=>v.starts),[1,1]);
  assert.equal(player.playing,true);
});
test('las diferencias pequeñas se corrigen sin saltos de fotograma',async t=>{
  const {player,videos}=setup(t);
  await player.play();
  videos[0]._time=.9;videos[1]._time=1;
  const writes=videos.map(v=>v.seeks);
  player.tick();
  assert.deepEqual(videos.map(v=>v.seeks),writes);
  assert.ok(videos[0].playbackRate>1&&videos[0].playbackRate<=1.03);
});
test('el avance respeta FPS fraccionarios y posiciona ambos videos',async t=>{
  const {player,videos}=setup(t);
  player.configure([{fps:30000/1001,frames:60},{fps:30000/1001,frames:60}]);
  await player.seekFrame(51);
  assert.deepEqual(videos.map(v=>v.currentTime),[51*1001/30000,51*1001/30000]);
  assert.equal(player.frame(),51);
  assert.equal(player.playing,false);
});
test('cancelar una carga no arranca después ni deja esperas pendientes',async t=>{
  const {player,videos,errors}=setup(t,0);
  const pending=player.play();player.stop();
  await pending;
  videos[1].readyState=4;videos[1].dispatchEvent(new Event('canplay'));
  assert.deepEqual(videos.map(v=>v.starts),[0,0]);
  assert.equal(player.pending.size,0);
  assert.deepEqual(errors,[]);
});
test('la repetición reinicia ambos videos en conjunto',async t=>{
  const {player,videos}=setup(t,4,{loop:()=>true});
  await player.play();videos.forEach(v=>v._time=2);
  videos[1].dispatchEvent(new Event('ended'));
  await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(videos.map(v=>v.currentTime),[0,0]);
  assert.equal(player.playing,true);
  assert.ok(videos.every(v=>v.loop===false));
});
