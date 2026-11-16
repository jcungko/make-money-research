const TF=900000, LIMIT=0.0075, KEY='btc-15m-move-alert-v1';
async function getCandle(now) {
  const start=Math.floor(now/TF)*TF;
  try {
    const url='https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=15m&startTime='+start+'&limit=1';
    const r=await fetch(url,{signal:AbortSignal.timeout(8000),headers:{accept:'application/json'}});
    if(!r.ok) throw new Error('Binance HTTP '+r.status);
    const j=await r.json();
    if(!Array.isArray(j)||!j.length||Number(j[0][0])!==start)throw new Error('Binance candle missing');
    return {open:Number(j[0][1]),price:Number(j[0][4]),high:Number(j[0][2]),low:Number(j[0][3]),t:start,source:'Binance BTCUSDT USD-M Futures'};
  } catch(e) {
    console.log('Binance unavailable; using Gate.io reference:',String(e).slice(0,110));
    const r=await fetch('https://api.gateio.ws/api/v4/futures/usdt/candlesticks?contract=BTC_USDT&interval=15m&limit=3',{signal:AbortSignal.timeout(8000)});
    if(!r.ok)throw new Error('Gate.io HTTP '+r.status);
    const j=await r.json();const c=j.find(x=>Number(x.t)*1000===start);
    if(!c)throw new Error('Gate.io candle missing');
    return {open:Number(c.o),price:Number(c.c),high:Number(c.h),low:Number(c.l),t:start,source:'Gate.io BTC_USDT Perpetual (fallback)'};
  }
}
async function notify(env,text){
  if(!env.TELEGRAM_BOT_TOKEN||!env.TELEGRAM_CHAT_ID)throw Error('Telegram secrets unavailable');
  const r=await fetch('https://api.telegram.org/bot'+env.TELEGRAM_BOT_TOKEN+'/sendMessage',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({chat_id:env.TELEGRAM_CHAT_ID,text}),signal:AbortSignal.timeout(10000)});
  const j=await r.json();if(!r.ok||!j.ok)throw Error('Telegram delivery failed '+r.status+': '+(j.description||'error'));
}
async function scan(env){
  if(!env.R146_STATE)throw Error('KV binding missing');
  const now=Date.now(),c=await getCandle(now);
  if(!Number.isFinite(c.open)||!Number.isFinite(c.price)||c.open<=0||c.price<=0)throw Error('Bad candle data');
  const movement=(c.price/c.open-1)*100;
  if(Math.abs(movement)<LIMIT*100)return {status:'below_threshold',move_percent:movement};
  const key=KEY+':'+c.t;
  if(await env.R146_STATE.get(key))return {status:'already_alerted'};
  const vn=new Date(c.t+7*3600000).toISOString().slice(0,16).replace('T',' ');
  const observed=new Date(now+7*3600000).toISOString().slice(0,19).replace('T',' ');
  const dir=movement>0?'📈 TĂNG':'📉 GIẢM';
  const message=['🚨 BTC BIẾN ĐỘNG 15 PHÚT >= 0,75%',dir+' '+movement.toFixed(3)+'% so với GIÁ MỞ NẾN','Mở nến: '+c.open.toFixed(2)+' USDT','Giá kiểm tra: '+c.price.toFixed(2)+' USDT','Nến bắt đầu (VN): '+vn,'Phát hiện (VN): '+observed,'Nguồn: '+c.source,'Dữ liệu nến đang chạy, chưa đóng. Chỉ cảnh báo biến động, KHÔNG phải tín hiệu giao dịch.'].join('\n');
  await notify(env,message);
  await env.R146_STATE.put(key,'1',{expirationTtl:3600});
  return {status:'sent',move_percent:movement};
}
const btcAlertWorker = {
  async scheduled(event,env,ctx){ctx.waitUntil(scan(env).then(r=>console.log('BTC alert:',JSON.stringify(r))).catch(e=>console.error('BTC alert failed:',String(e))));},
  async fetch(){return new Response('BTC 15m Telegram movement alerts. Trading and research are disabled.',{headers:{'content-type':'text/plain; charset=utf-8'}});}
};
// --- USDJPY Research-only Telegram notifications (no Telegram secrets in GitHub) ---
const USDJPY_AUD = 'make-money-usdjpy-notifier-v1';
const USDJPY_WORKFLOW = 'jcungko/make-money-research/.github/workflows/usdjpy-research-autopilot.yml@refs/heads/main';
function usdB64url(s) {
  const v=s.replace(/-/g,'+').replace(/_/g,'/');
  const b=atob(v+'='.repeat((4-v.length%4)%4));
  return Uint8Array.from(b,c=>c.charCodeAt(0));
}
async function authenticateGithubOidc(request) {
  const auth=request.headers.get('authorization')||'';
  if (!auth.startsWith('Bearer ')||auth.length>12000) throw Error('missing OIDC');
  const token=auth.slice(7).trim(),parts=token.split('.');
  if(parts.length!==3) throw Error('bad JWT');
  const hdr=JSON.parse(new TextDecoder().decode(usdB64url(parts[0])));
  const claims=JSON.parse(new TextDecoder().decode(usdB64url(parts[1])));
  const now=Math.floor(Date.now()/1000);
  if (hdr.alg!=='RS256'||typeof hdr.kid!=='string') throw Error('unsupported JWT');
  if(claims.iss!=='https://token.actions.githubusercontent.com' ||
     claims.aud!==USDJPY_AUD ||
     claims.repository!=='jcungko/make-money-research' ||
     claims.ref!=='refs/heads/main' ||
     claims.workflow_ref!==USDJPY_WORKFLOW ||
     (claims.job_workflow_ref && claims.job_workflow_ref!==USDJPY_WORKFLOW) ||
     !Number.isInteger(claims.iat)||!Number.isInteger(claims.exp)||
     claims.iat>now+60||claims.exp<now||claims.exp>now+1200) throw Error('wrong GitHub identity');
  const res=await fetch('https://token.actions.githubusercontent.com/.well-known/jwks',
       {signal:AbortSignal.timeout(6000),headers:{accept:'application/json'}});
  if(!res.ok)throw Error('OIDC key fetch failed');
  const jwks=await res.json();
  const jwk=(jwks.keys||[]).find(x=>x.kid===hdr.kid&&x.kty==='RSA');
  if(!jwk)throw Error('OIDC key not found');
  const key=await crypto.subtle.importKey('jwk',jwk,{name:'RSASSA-PKCS1-v1_5',hash:'SHA-256'},false,['verify']);
  const valid=await crypto.subtle.verify('RSASSA-PKCS1-v1_5',key,usdB64url(parts[2]),
                         new TextEncoder().encode(parts[0]+'.'+parts[1]));
  if(!valid)throw Error('OIDC signature invalid');
  return claims;
}
async function handleUsdNotify(request,env) {
  try {
    await authenticateGithubOidc(request);
    const p=await request.json();
    const allowed=['TEST','CANDIDATE','EXHAUSTED','ERROR'];
    if(!p||!allowed.includes(p.kind)||!Number.isSafeInteger(p.run_id)||p.run_id<=0||
       !Number.isSafeInteger(p.cursor)||p.cursor<0||p.cursor>96||
       !Array.isArray(p.candidates)||p.candidates.length>2||
       !p.candidates.every(x=>/^UJ-R1-[0-9]{3}$/.test(x))) throw Error('invalid payload');
    if(p.kind==='CANDIDATE'&&p.candidates.length===0)throw Error('empty candidates');
    if(!env.R146_STATE)throw Error('KV not connected');
    const key='usdjpy-notifier-v1:'+(p.kind==='EXHAUSTED'?'EXHAUSTED-R1':p.kind+':'+p.run_id);
    if(await env.R146_STATE.get(key)) return new Response('duplicate ignored',{status:200});
    const run='https://github.com/jcungko/make-money-research/actions/runs/'+p.run_id;
    let message;
    if(p.kind==='TEST') message='✅ MAKE MONEY — USDJPY Telegram đã kết nối. Đây là tin nhắn KIỂM TRA, không phải tín hiệu hoặc kết quả có lãi.';
    else if(p.kind==='CANDIDATE') message='🧪 MAKE MONEY — ỨNG VIÊN USDJPY cần kiểm toán độc lập: '+p.candidates.join(', ')+'. Chỉ là RESEARCH_CANDIDATE trên dữ liệu lịch sử, CHƯA chứng minh lợi nhuận thật.';
    else if(p.kind==='EXHAUSTED') message='📋 MAKE MONEY — Vòng nghiên cứu USDJPY R1 đã hết 96 giả thuyết đăng ký; cần đánh giá lại giả thuyết trước khi nghiên cứu tiếp.';
    else message='⚠️ MAKE MONEY — USDJPY Autopilot gặp lỗi chạy hoặc checkpoint, cần kiểm tra GitHub Actions.';
    message+='\nTiến độ cursor: '+p.cursor+'/96\nBằng chứng: '+run+'\nKHÔNG phải lệnh giao dịch.';
    await notify(env,message);
    await env.R146_STATE.put(key,'sent',{expirationTtl:60*60*24*90});
    return new Response('sent',{status:200});
  } catch(err) {
    console.error('USDJPY secure notifier failure:',String(err).slice(0,160));
    return new Response('not delivered',{status:403});
  }
}
export default {
  scheduled: btcAlertWorker.scheduled,
  async fetch(request,env,ctx) {
    if(new URL(request.url).pathname==='/notify-usdjpy'&&request.method==='POST'){
      return handleUsdNotify(request,env);
    }
    return btcAlertWorker.fetch(request,env,ctx);
  }
};
