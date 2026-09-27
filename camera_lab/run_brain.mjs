// Uses the downloaded model unchanged. Replay one held camera frame plus controls.
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { BrainCPU } from '../fruit-fly-simulation/src/brain.js';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const inputPath=path.resolve(process.argv[2]);
const input=JSON.parse(fs.readFileSync(inputPath));
const dir=path.join(root,'fruit-fly-simulation/public/data');
const manifest=JSON.parse(fs.readFileSync(path.join(dir,'manifest.json')));
const neurons=JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(dir,manifest.metadata))));
const graph={n:manifest.neurons,neurons,sign:Int32Array.from(neurons,r=>['dopamine','octopamine','serotonin'].includes(r[4])?1:r[5])};
for(const a of manifest.arrays){
  const values=new Uint32Array(a.length); let offset=0;
  for(const part of a.parts){
    const compressed=fs.readFileSync(path.join(dir,part.file));
    if(crypto.createHash('sha256').update(compressed).digest('hex')!==part.sha256)throw Error('Checksum failed: '+part.file);
    const b=zlib.gunzipSync(compressed);
    const chunk=new Uint32Array(b.buffer,b.byteOffset,b.byteLength/4);
    values.set(chunk,offset); offset+=chunk.length;
  }
  if(offset!==a.length)throw Error('Length mismatch'); graph[a.name]=values;
}
const rates=new Float32Array(graph.n), injected=new Set();
for(const c of input.channels){
  if(String(neurons[c.index][0])!==c.bodyId || neurons[c.index][1]!=='L2')throw Error('Mapping mismatch');
  if(!Number.isFinite(c.rate_hz)||c.rate_hz<0||c.rate_hz>120)throw Error('Bad rate');
  rates[c.index]=c.rate_hz; injected.add(c.index);
}
const brain=new BrainCPU(graph,{seed:1});
const runs={};
for(const condition of ['no_input','camera','connections_off']){
  brain.reset(); const started=performance.now();
  const result=brain.batch(500,condition==='no_input'?new Float32Array(graph.n):rates,condition==='connections_off');
  const active=[]; let downstreamSpikes=0;
  for(let i=0;i<graph.n;i++)if(result.counts[i]){
    if(!injected.has(i))downstreamSpikes+=result.counts[i];
    active.push({bodyId:String(neurons[i][0]),type:neurons[i][1],side:neurons[i][3],
                 spikes:result.counts[i],injected:injected.has(i)});
  }
  active.sort((a,b)=>b.spikes-a.spikes);
  runs[condition]={model_ms:50,wall_ms:performance.now()-started,total_spikes:result.total,
                   active_neurons:active.length,downstream_spikes:downstreamSpikes,
                   top_downstream:active.filter(x=>!x.injected).slice(0,20)};
  fs.writeFileSync(path.join(path.dirname(inputPath),condition+'_spikes.json'),JSON.stringify(active));
  console.log(condition,JSON.stringify(runs[condition]));
}
const passed=runs.no_input.total_spikes===0&&runs.camera.downstream_spikes>0&&runs.connections_off.downstream_spikes===0;
const report={model:'Unmodified Xenova BrainCPU / MaleCNS',neurons:graph.n,edges:graph.sources.length,
  input:inputPath,scope:'Single RGB-D snapshot held for 50 ms model time. Does not establish perception, live throughput or biological validity.',runs,propagation_check_passed:passed};
fs.writeFileSync(path.join(path.dirname(inputPath),'brain_report.json'),JSON.stringify(report,null,2));
if(!passed)process.exitCode=1;
