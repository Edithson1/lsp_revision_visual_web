'use strict';
class ComparisonPlayer {
  constructor(videos, {onState=()=>{},onTime=()=>{},onError=()=>{},onStats=()=>{},loop=()=>false}={}) {
    Object.assign(this,{videos,onState,onTime,onError,onStats,loop});
    this.rate=1;this.fps=30000/1001;this.frames=1;this.generation=0;this.intent=false;this.playing=false;this.pending=new Set();
    for(const video of videos) {
      video.loop=false;
      video.addEventListener('ended',()=>{if(this.intent){if(this.loop())this.play(0);else this.stop();}});
      video.addEventListener('waiting',()=>{if(this.playing&&video.readyState<3)this.play();});
      video.addEventListener('error',()=>{if(this.intent){this.stop();this.onError('No se pudo cargar la comparación. Vuelve a abrir este registro.');}});
    }
    this.timer=setInterval(()=>this.tick(),100);
  }
  active() {return this.videos.filter(v=>v.getAttribute('src')&&!v.error);}
  configure(timings) {
    const valid=timings.filter(Boolean);
    this.fps=valid.at(-1)?.fps||30000/1001;
    this.frames=valid.length?Math.max(1,Math.min(...valid.map(t=>t.frames))):1;
    this.onTime(this.frame(),this.frames,this.fps);
  }
  frame() {return Math.max(0,Math.min(this.frames-1,Math.floor((this.videos.at(-1).currentTime||0)*this.fps+1e-4)));}
  stop() {
    ++this.generation;this.intent=false;this.playing=false;
    [...this.pending].forEach(cancel=>cancel());
    for(const v of this.videos){v.pause();v.playbackRate=this.rate;}
    this.onState('Pausado',false);
  }
  ready(video, token) {
    if(video.readyState>=3&&!video.seeking)return Promise.resolve();
    return new Promise((resolve,reject)=>{
      const events=['canplay','canplaythrough','seeked','loadeddata','error','abort'];
      let timeout,settled=false;
      const done=error=>{if(settled)return;settled=true;clearTimeout(timeout);this.pending.delete(done);events.forEach(e=>video.removeEventListener(e,check));error?reject(error):resolve();};
      const check=()=>{
        if(token!==this.generation)return done();
        if(video.error)return done(new Error('No se pudo preparar uno de los videos.'));
        if(video.readyState>=3&&!video.seeking)done();
      };
      events.forEach(e=>video.addEventListener(e,check));
      this.pending.add(done);
      timeout=setTimeout(()=>done(new Error('La carga está tardando. Espera a que terminen de aparecer ambos videos e intenta reproducir.')),120000);
    });
  }
  seekMedia(video,time) {
    if(video.readyState<1)return Promise.resolve();
    time=Math.max(0,Math.min(time,Math.max(0,video.duration-1/this.fps)));
    if(Math.abs(video.currentTime-time)<.0001&&!video.seeking)return Promise.resolve();
    return new Promise((resolve,reject)=>{
      let settled=false;
      const finish=error=>{if(settled)return;settled=true;clearTimeout(timer);this.pending.delete(finish);video.removeEventListener('seeked',done);error?reject(error):resolve();};
      const done=()=>finish();
      const timer=setTimeout(()=>finish(new Error('No se pudo posicionar un video.')),15000);
      this.pending.add(finish);
      video.addEventListener('seeked',done,{once:true});
      video.currentTime=time;
    });
  }
  async play(startAt) {
    const token=++this.generation;
    [...this.pending].forEach(cancel=>cancel());
    this.intent=true;this.playing=false;
    this.videos.forEach(v=>v.pause());
    this.onState('Preparando ambos videos…',false,true);
    const videos=this.active();
    try {
      if(!videos.length)throw new Error('No hay videos disponibles.');
      await Promise.all(videos.map(v=>this.ready(v,token)));
      if(token!==this.generation||!this.intent)return;
      let time=startAt??this.videos.at(-1).currentTime;
      if(time>=(this.frames-1)/this.fps)time=0;
      await Promise.all(videos.map(v=>this.seekMedia(v,time)));
      if(token!==this.generation||!this.intent)return;
      videos.forEach(v=>{v.loop=false;v.playbackRate=this.rate;});
      await Promise.all(videos.map(v=>v.play()));
      if(token!==this.generation||!this.intent){if(!this.intent)videos.forEach(v=>v.pause());return;}
      this.playing=true;this.onState('Reproduciendo',true);
    }catch(error){if(token===this.generation){this.stop();this.onError(error.message);}}
  }
  async seekFrame(number) {
    this.stop();const token=this.generation;
    number=Math.max(0,Math.min(this.frames-1,number));
    try {await Promise.all(this.active().map(v=>this.seekMedia(v,number/this.fps)));}
    catch(error){if(token===this.generation)this.onError(error.message);}
    if(token===this.generation)this.onTime(number,this.frames,this.fps);
  }
  setRate(rate) {this.rate=rate;this.videos.forEach(v=>v.playbackRate=rate);}
  tick() {
    if(this.playing) {
      const [reference,simulated]=this.videos;
      if(simulated.currentTime>=(this.frames-.5)/this.fps){if(this.loop())this.play(0);else this.stop();return;}
      if(reference.readyState>=3&&simulated.readyState>=3) {
        // Corregir pequeñas diferencias con velocidad, sin saltos de currentTime.
        const drift=simulated.currentTime-reference.currentTime;
        reference.playbackRate=this.rate*(Math.abs(drift)<.018?1:Math.max(.97,Math.min(1.03,1+drift*.3)));
      }
      this.onTime(this.frame(),this.frames,this.fps);
    }
    this.onStats(this.videos.map(v=>{
      const q=v.getVideoPlaybackQuality?.();
      return {frames:q?.totalVideoFrames??0,dropped:q?.droppedVideoFrames??0,time:v.currentTime||0};
    }));
  }
}
if(typeof module!=='undefined')module.exports={ComparisonPlayer};
