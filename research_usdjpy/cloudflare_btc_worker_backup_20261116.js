// Backup for rollback. No Telegram secret values are included.
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
export default {
  async scheduled(event,env,ctx){ctx.waitUntil(scan(env).then(r=>console.log('BTC alert:',JSON.stringify(r))).catch(e=>console.error('BTC alert failed:',String(e))));},
  async fetch(){return new Response('BTC 15m Telegram movement alerts. Trading and research are disabled.',{headers:{'content-type':'text/plain; charset=utf-8'}});}
};