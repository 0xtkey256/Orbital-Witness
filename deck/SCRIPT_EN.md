# Orbital Witness — Pitch script

## Slide 1

Hi, I'm Taiki. This is Orbital Witness: we put satellites on the witness stand.

## Slide 2

In the AI era, a fake flood photo costs nothing to make, and it spreads faster than any newsroom can check it.  
  
The obvious fix is to ask an LLM to fact-check. But an LLM writes a convincing reason after the fact, it can argue either side, and nobody can re-run its decision.  
  
Now agents are starting to pay insurance claims and allocate aid based on claims like these. A machine that pays out needs evidence a machine can audit.

## Slide 3

So our rule is: don't let AI decide — let it design the experiment.  
  
The AI turns a claim into a hypothesis: where, when, and what a satellite should see if it's true. Then we seal that plan with SHA-256 before reading a single pixel.  
  
We compare against the same season last year, a skeptic agent lists rival explanations, and the verdict comes from a formula, not the model. The AI even tried to raise thresholds after sealing. Those proposals are logged and never applied.

## Slide 4

[Point along the flow] A claim comes in, the Scout looks for news, the Planner and Skeptic design the experiment, and the Seal locks it.  
  
Then satellite and weather probes run in parallel Daytona sandboxes, and CodeAF repairs any that crash.  
  
Finally the Ledger decides by formula, and the Judge only explains what it sees in the images.

## Slide 5

Five partner technologies, each with one job:  
- AgentField orchestrates three nodes and discovers sensor probes at runtime.  
- Tavily searches news for and against the claim.  
- Nosana hosts Qwen2.5-VL on a GPU for planning, skepticism and reading images.  
- Daytona runs each satellite probe in its own sandbox, in parallel.  
- CodeAF repairs probe code that crashes.  
  
[→ Switch to the website]

## Slide 6

[Website: Featured case → True claim]  
Here's a real run. The claim: record rain flooded Dubai airport on April 16th, 2024.  
[Drag the slider] Sentinel-2 sees new water around the airport: plus 1.1 percent of the area, with a confidence interval that clears our sealed threshold. ERA5 shows rain twenty standard deviations above normal.  
[Point at the gauge] Verdict: supported, 0.91, and that number is computed, not generated.  
  
[Switch to False claim]  
Now the same story with the place swapped: 'Cairo airport flooded.' This is a classic misinformation pattern.  
[Pause] No new water, normal rainfall. Contradicted, 0.045. The satellite caught the lie.  
  
[Scroll to the ledger and plan log] Every line is auditable: sealed hash, scene IDs, the exact probe code.  
  
[→ Back to the slides]

## Slide 7

This works for newsroom fact-checking, parametric insurance, humanitarian damage triage, and deforestation due diligence: anywhere a claim about the physical world needs evidence.  
  
Every run leaves an evidence bundle: the sealed hash, the satellite scene IDs, and the probe code fingerprint. Anyone who re-runs it gets the same verdict.

## Slide 8

Orbital Witness: don't let AI decide — let it design the experiment. It's live, and the code is on GitHub. Thank you.  
  
[Likely questions]  
- Why not just an LLM? It can't be audited or re-run, and it moves goalposts. We sealed the plan before seeing data.  
- Clouds? Cloudy pixels are masked out. SAR, which sees through cloud, is built in as an optional probe.  
- Beyond floods? Fire, deforestation and construction signatures are already defined. New sensors are just new probes AgentField discovers.
