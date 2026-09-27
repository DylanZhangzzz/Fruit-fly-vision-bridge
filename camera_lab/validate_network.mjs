// Exhaustive address/propagation audit of the unchanged full BrainCPU model.
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {BrainCPU} from '../fruit-fly-simulation/src/brain.js';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const dir=path.join(root,'fruit-fly-simulation/public/data');
const out=path.join(root,'camera_lab/validation');
const manifest=JSON.parse(fs.readFileSync(path.join(dir,'manifest.json')));
const neurons=JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(dir,manifest.metadata))));
const graph={n:manifest.neurons,neurons,sign:Int32Array.from(neurons,r=>['dopamine','octopamine','serotonin'].includes(r[4])?1:r[5])};
for(const a of manifest.arrays){
  const values=new Uint32Array(a.length);let offset=0;
  for(const part of a.parts){
    const compressed=fs.readFileSync(path.join(dir,part.file));
    if(crypto.createHash('sha256').update(compressed).digest('hex')!==part.sha256)throw Error('Bad data hash');
    const b=zlib.gunzipSync(compressed),chunk=new Uint32Array(b.buffer,b.byteOffset,b.byteLength/4);
    values.set(chunk,offset);offset+=chunk.length;
  }
  if(offset!==a.length)throw Error('Length mismatch');graph[a.name]=values;
}
const input=JSON.parse(fs.readFileSync(path.join(process.env.FLYVISION_LEGACY_CAPTURE || path.join(root,'camera_lab/captures/legacy'),'neural_input.json')));
const brain=new BrainCPU(graph,{seed:1}),rates=new Float32Array(graph.n);
const zero=brain.batch(1000,rates);
if(zero.total!==0)throw Error('Zero-input control failed');
const rows=[],started=performance.now();
for(const [ordinal,c] of input.channels.entries()){
  if(String(neurons[c.index][0])!==c.bodyId||neurons[c.index][1]!=='L2'||neurons[c.index][3]!=='R')throw Error('Address mismatch');
  rates.fill(0);rates[c.index]=120;
  const row={bodyId:c.bodyId,index:c.index,model_ms:100,drive_hz:120};
  for(const [name,silenced] of [['connected',false],['disconnected',true]]){
    brain.reset();const result=brain.batch(1000,rates,silenced);
    let downstream=0,active=0;const top=[];
    for(let i=0;i<graph.n;i++)if(i!==c.index&&result.counts[i]){
      downstream+=result.counts[i];active++;
      top.push({bodyId:String(neurons[i][0]),type:neurons[i][1],spikes:result.counts[i]});
    }
    top.sort((a,b)=>b.spikes-a.spikes);
    row[name]={target_spikes:result.counts[c.index],downstream_spikes:downstream,
      downstream_active:active,top:top.slice(0,5)};
  }
  row.address_control_passed=row.disconnected.target_spikes>0&&row.disconnected.downstream_spikes===0;
  row.propagation_observed=row.connected.downstream_spikes>0;
  rows.push(row);
  if((ordinal+1)%100===0)console.log(`${ordinal+1}/${input.channels.length}`);
}
const summary={neurons:graph.n,edges:graph.sources.length,tested:rows.length,seed:1,
  model_ms_per_condition:100,drive_hz:120,zero_input_spikes:zero.total,
  address_passed:rows.filter(r=>r.address_control_passed).length,
  propagation_observed:rows.filter(r=>r.propagation_observed).length,
  no_propagation_ids:rows.filter(r=>!r.propagation_observed).map(r=>r.bodyId),
  wall_seconds:(performance.now()-started)/1000,
  scope:'Each L2 injected alone at 120 Hz for 100 ms; same seed and reset for connected/disconnected. Address verification, not visual-field or behavior validation.',
  model_sha256:crypto.createHash('sha256').update(fs.readFileSync(path.join(root,'fruit-fly-simulation/src/brain.js'))).digest('hex')};
fs.writeFileSync(path.join(out,'network_neurons.json'),JSON.stringify(rows,null,2));
fs.writeFileSync(path.join(out,'network_summary.json'),JSON.stringify(summary,null,2));
console.log(JSON.stringify(summary,null,2));
if(summary.address_passed!==rows.length)process.exitCode=1;
