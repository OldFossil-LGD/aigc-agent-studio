# Higgsfield workflow notes from public sources

Date: 2026-10-18
Sources: Higgsfield official site/blog, OpenAI case study, Higgsfield MCP docs, community skills.

These are historical research notes. Model lists, billing statements and account observations describe the sources and sessions recorded here. Case-study results are attributed reports. Check current interfaces and terms before using them. The suggestions for aigc-agent-studio are design proposals.

## 1. Platform shape
- Web-based all-in-one creative suite: Image, Video, Audio, Edit, Canvas, MCP/API.
- Multi-model generation: Seedance 2.0/2.5, Kling 2.5/3.0, Veo 3.1, Wan 2.5/2.6/2.7, Sora 2, MiniMax Hailuo, etc.
- Cinematic logic layer: planning (narrative arc, camera logic, pacing, visual emphasis) before generation.
- Character consistency: Soul ID (train from 20+ photos), Soul character reuse across models.
- Audio: native audio in some models (Veo 3.1), LipSync Studio, voice cloning/dubbing.
- Marketing: Ads Studio, UGC/TV spot presets, brand kits.

## 2. Agentic generation workflow (MCP/CLI)
1. Connect agent (Claude/ChatGPT/Cursor/Hermes) to Higgsfield MCP or CLI.
2. User describes shot in natural language; agent may ask for credit cost confirmation.
3. Agent selects model and sets parameters (duration, aspect ratio, resolution, references).
4. Generation runs asynchronously; returns job id.
5. Poll job status; display result.
6. Iterate: change model, angle, variants, or batch.

## 3. Model routing (public guidance)
- Realistic person speaking: Kling 3.0
- Cinematic scene with audio: Veo 3.1
- Product/food in motion: MiniMax Hailuo
- Controlled narrative sequence: Runway Gen-4.5
- First-to-last-frame transition: Wan 2.6
- Commercial multi-reference: Seedance 2.0
- Stylized multi-shot: Kling 3.0
- Fast iteration: Hailuo

## 4. Input modalities
- Text-to-video, image-to-video
- Multi-image reference for character consistency
- First/last frame interpolation
- Video-to-video restyle
- Audio-driven lip sync
- Pose/sketch references

## 5. Production controls
- Resolution ladder: start 720p for iteration, then 1080p/4K
- Duration: model-dependent (2-15s typical)
- Aspect ratio: platform/distribution-specific
- Credits: standard rates; unlimited/free generations do not apply to agent-based generations

## 6. MCP tool surface (public)
- generate_image / generate_video (credit-consuming)
- models_explore (model constraints)
- job_status / job_display
- media_upload / media_confirm
- presets_show
- balance / show_plans_and_credits
- select_workspace

## 7. Workflow distillation for aigc-agent-studio
- Planning-first mirrors our production compiler: intent → shot contract → model routing → generation → review.
- Record model routing in a policy table that maps shot type to model.
- Character consistency should be represented as reusable asset (Soul ID) in asset graph.
- Native audio models reduce post-production; keep audio node optional based on model.
- Async job polling + status tracking belongs in platform adapter, with retries and idempotency.
- Credit/cost estimation should be part of preflight before generation.
- Multi-model comparison can be a first-class candidate workflow (A/B/C candidates).

## 8. Connection status
- Higgsfield MCP connector is configured but pending authorization.
- Live tool calls return CONNECTION_REQUIRED until the user completes authorization.

## 9. Live model inventory (connected account, free plan)
Key video models available via MCP:
- Cinema Studio Video 3.0: 4-15s, cinematic, premium, audio optional
- Cinema Studio Video: 5/10s, dramatic, sound default on
- Cinema Studio Video v2: 3-12s, genre/mode/sound/speedramp/multi-shot
- Marketing Studio: 12-15s, ads/UGC, avatar/product support
- FLUX 3 Video: 5-20s, text/image/video continuation, audio
- Grok Imagine Video 1.5: 2-15s, audio
- Minimax Hailuo: 6/10s, physics/emotion/facial
- MiniMax H3/H3 Max: 4-15s, 2K, audio references
- Wan 2.6: 5/10/15s, stylized
- Seedance 1.5 Pro: 4/8/12s, audio
- Seedance 2.0: 4-15s, reference-driven, audio, supports unlimited trials
- Seedance 2.0 Mini: 4-15s, budget, audio

Model routing needs duration limits and audio capabilities. Parallel candidates could be used to compare models.

## 10. Canvas workflow distillation (public)
Canvas is a node-based infinite board: prompt → image → video → edit, with typed connections and fan-out.

Named patterns:
- Simple Seedance 2.0: image + prompt → video (minimal)
- Extend Video: sequential chain, last frame feeds next (longer continuous)
- Image Edit: multi-reference compositing into one generator
- StoryBoard With Elements: Assets → Story → Prompts columns, often with LLM node shaping prompts
- Long Video (fan-out): one reference set fanned into several shot prompts for multi-shot assembly

Reference handling:
- Group references by function: identity, product geometry, composition, environment, palette, light, wardrobe, texture, negative examples
- Describe reference role explicitly in prompt (not just connect)
- Seedance: connected image is character/location/product reference
- Kling: connected image is start frame; character/element references require element tags
- Audio nodes attach to video nodes for voice/VO/sync

Production discipline:
- Name each board by decision, owner, review date, definition of done
- Separate discovery from approved material
- Log credit-consuming actions; stop after approved composition
- Handoff package: exported visual, composition contract, authorized sources, protected/flexible/forbidden details, version history, reviewer, approval date

Case study (Big Purple / Türkiye Wealth Fund):
- Kept 5 creative stages: casting, wardrobe, location, storyboard, shooting
- AI replaced physical shoot; same creative decisions
- Pre-production references moved from studio walls to Canvas
- Revisions became fast and precise ("Revision-Proof AI Films")
- 10-12 days vs ~2 months traditional (~80% time saving)

## 11. Extended model routing (live)
- Cinema Studio 4.0: 4-30s, t2v/omni_reference/video_edit/video_extension, audio, lighting/camera/color controls
- Seedance 2.5: 4-30s, t2v/omni_reference/video_edit/video_extension, draft/finalize, audio
- Kling 3.0: 3-15s, multi-shot, audio, 4K
- Kling 3.0 Omni: 3-15s, multi-shot, multi_prompt, 4K
- Kling 3.0 Omni Edit: video edit with references
- FLUX 3 Video: 5-20s, start/end/image references, audio
- MiniMax H3/H3 Max: 4-15s, 2K/768p, audio refs
- Grok Imagine Video 1.5: 1-15s, audio
- Kling 2.6: 5/10s, audio
- Kling 3.0 Turbo: 3-15s, fast
- Happy Horse Video: 3-15s
- Wan 2.6: 5/10/15s, stylized
- Seedance 2.0/Mini: 4-15s, reference-driven, audio, unlim
- Ad Multiplier / Recreate: ad structure reuse, localization, hook/CTA regeneration
- Topaz Hyperion/Topaz: upscale/deflicker/reframe
- Draw To Video / Reframe / Video Upscale / Deflicker: post-processing

Multi-shot capability:
- Kling 3.0/Omni support multi_shots + multi_prompt
- Cinema Studio 4.0 supports scene extension and editing
- Seedance 2.5 supports video_extension (forward/backward)

A routing policy could map shot_kind/segmented to multi-shot models and use extension for long sequences.

## 12. Canvas node-graph templates (distilled)
Node categories:
- Prompt (text starting points)
- Image generator
- Video generator
- Voice/audio generator
- LLM assistant (prompt shaping)
- Style/motion transfer
- Render output
- References: Upload / Assets

Typed connections: image output -> image input, prompt -> generator, etc. Fan-out free; fan-in structured.

Reusable templates:
1. Simple Seedance 2.0: image + prompt -> video
2. Extend Video: last frame feeds next (longer continuous)
3. Image Edit: multi-reference compositing -> one image generator
4. StoryBoard With Elements: Assets -> Story -> Prompts columns, LLM shapes prompts
5. Long Video (fan-out): one reference set fanned into several shot prompts for multi-shot assembly

Operational rules:
- Building/connecting/editing is free; credits only on generate
- Credits deducted per node generation at model rates
- Unlimited models cannot be used in Canvas
- Autosave periodic; hard refresh restores latest autosave
- Collaboration: multiple users can add nodes/connect/trigger; outputs appear in real time

Reference handling:
- Seedance: connected image is character/location/product reference; describe role in prompt
- Kling: connected image is start frame; character/element refs require @element tag
- Audio nodes attach to video nodes for VO/sync

The shot graph follows the Canvas node structure. compile_shot_graph could target its templates, using fan-out for multiple shots and extension for long takes.

## 13. Agentic video generation procedure (distilled)
1. Connect agent to platform (MCP/CLI); verify with read-only call (balance/models).
2. Convert brief into shot-level plan: subject, setting, mood, duration, aspect ratio, resolution.
3. Explore available models and constraints before generation.
4. Route each shot to a model by shot needs (realism, audio, motion, transitions).
5. Confirm credit cost and parameters before spending credits.
6. Submit generation asynchronously; capture job/request id.
7. Poll job status until completion; display/download result.
8. Iterate by changing model/angle/parameters; reuse character/brand assets for continuity.

Multi-shot: use Kling 3.0/Omni multi_shots + multi_prompt.
Long sequences: use Seedance 2.5 video_extension (forward/backward).
Native audio: choose models with audio when sound required.
Character consistency: train Soul ID (20+ photos) and reuse across models.

## 14. Case study distillation: PURGA (Cannes Lions Bronze, Film)
Workflow principle: fix characters and visual direction first, then build the world around them.
- Character-first sequence: casting → lenses → framing → camera position → visual consistency inside one system.
- Instead of generating images one prompt at a time and matching afterward, develop characters first, then explore shots around them.
- Consistency becomes maintained as you go, not recovered after the fact.
- Cinema Studio carries character creation and shot/image development: casting, lenses, framing, camera position, visual consistency.
- Animation and music handled by other AI tools in the stack (hybrid).
- Value metric: reach the desired image sooner; reinvest saved time into thinking, experimenting, directing, refining.
- Iteration makes variation practical; approvals stay flexible longer; clients see alternatives while direction is still being shaped.

For aigc-agent-studio, lock assets and characters before shot generation and record visual direction (style + camera) in the contract.

## 15. Case study distillation: Big Purple / Dreaming Broccoli (Türkiye Wealth Fund)
Traditional baseline: 30 days pre-prod + 5 days shoot + 20 days post.
AI result: 10-12 days including approvals/revisions (~80% faster).

Workflow preserved from traditional production:
- Five creative stages unchanged: casting, wardrobe, location, storyboard, shooting.
- Pre-production references (casting, wardrobe, scene) moved from studio walls to Canvas.
- Image/video generation replaces physical shoot; same creative decisions at every stage.

Key insight: "filmmaking knowledge has not changed; speed and possibilities for putting it into practice have."

Revision-Proof AI Films:
- Clients (banks) require precise brand details; even background extra T-shirt color can require revision.
- AI enables precise adjustments while preserving approved performances/emotion/atmosphere.
- Fast revisions without restarting entire scene.

Gradual adoption:
- Started with difficult wide shots (1950s Istanbul aerial from old photo).
- Expanded to whole film after proving value.

The studio could keep the traditional creative stages and use generation for execution. A canvas reference board would support changes at the detail level.

## 16. Case study distillation: Vertex CGI (NBA Finals viral campaign)
Workflow:
- Research audience/platform/culture first; define creative blueprint (key visual moments, pacing, structure).
- Production is execution of validated decisions.
- Hybrid pipeline: live footage + AI post (texturing, tracking, masking, env replacements) or full AI sequences.
- Higgsfield entered from the very first conversation: generate visuals live during calls to align stakeholders; "visual language is the easiest language for people to align around."
- Concept to publish in 5 days: ideation, storyboard, production, iteration, edit, delivery.
- Models: Nano Banana Pro + ChatGPT Image 2 for visual thinking/exploration; Kling 3.0 for production.
- Resolution ladder: 720p for iteration (speed > quality), 1080p for final.
- Result: SportsCenter pickup; weeks of traditional work compressed to 5 days.

Generated stills could help agree on visual direction before final production. The plan would also record resolution stages and audience needs, with AI and traditional tools used in the same workflow.

## 17. Case study distillation: BITT Animation (hybrid VFX + AI)
Workflow:
- Traditional stack (Maya, Houdini, Nuke, After Effects, DaVinci, Unreal) remains; AI augments.
- Hybrid shot: original plate -> Seedance edit (drop animated character, replace car, change background, swap product, add element) -> generated pass -> compositing stage (reconcile against original footage) -> final beauty pass/enhance/upscale.
- Generation does the hours-consuming part; traditional craft (plate management, comp, finishing) makes it hold up as a shot.
- Front of process replaced: concept artists + 3D previz over weeks -> now days; traditional route used when specific job calls for it.
- Platform consolidation: Higgsfield puts much of what was across 5 platforms into one organized place.
- Prompt systems developed internally and refined across projects; platform supplies models/control.
- Cinema Studio primary use: previz with clients, reaching real direction fast enough to converse same week; sometimes carries to final.
- MCP/CLI heavy use: wiring Higgsfield into BITT's own systems/automations; agent workflows for volume/unattended tasks.
- Team trained on one system; knowledge no longer siloed by specialist tool.
- Time/cost: 3-month work -> 3-6 weeks (some ~1 week); fully generative 15-20% of traditional budget; hybrid 30-40%.
- Capacity: 1 major project -> ~6 in parallel; bottleneck moved from studio to client feedback.
- Quality gate unchanged: composition, performance, timing, taste; technology changes how frame is made, not what is accepted.

A hybrid VFX workflow would follow plate -> generative pass -> comp -> finish. A shared platform and team training could reduce tool fragmentation.

## 18. Case study distillation: Sinecera (hybrid production, approval-gated pipeline)
Pipeline: script → boards → previz → offline → online, with client approval gate at every step.
Higgsfield sits from boards through to a large share of final imagery; "less a tool in the pipeline than the room the work happens in."

Cinema Studio as center:
- Dedicated project per job; whole team works inside it
- AI Cast + Soul ID hold a recurring face across a full commercial
- AI Locations hold a consistent world
- Cinematic Cameras for real camera language rather than one-off clips

Keyframe habit:
- Always work from an approved keyframe; art-direct and sign off a still, then move it.
- Text-to-video is the exception, not the default.
- Multishot is the workhorse for turning approved storyboard frames into moving shots across models without losing the approved frame.

Hybrid case (Nesine 100th Gazi Koşusu):
- Real spectators shot on green screen; everything behind them generated (hippodromes, crowds, eras, world aging across a century).
- Conventional version wasn't a more expensive option; it just wasn't an option.

Full-AI case (Lacoste x SuperStep):
- Built entirely in Cinema Studio: cast, locations, camera language in one project.
- Fashion demands consistency and taste; demonstrates platform when brief is mood rather than narrative.

Approval-gated value:
- Client's first sight of moving cut comes before money spent (vs conventional where first sight comes after spend).
- Being straight about seams builds trust; clients burned by AI vendors respond well.
- Most clients no longer ask whether made with AI; they ask whether we can deliver Thursday.

Cost/time:
- Shoot days: 3-4 -> 1 or none.
- Crew: 30-50 on location -> 5-6 core on full-AI.
- Revisions: from "reshoot" to "regenerate".

A stage-based workflow could require approval before moving from stills to motion. It would support multishot from approved frames and live plates with generated backgrounds, while making visible seams clear to clients.

## 19. Case study distillation: AdQUA (Korean digital agency + Boosterz)
Pain points before Higgsfield:
- Burden evaluating/learning many AI tools
- Different tasks required different platforms; subscriptions fragmented
- Inconsistent workflows due to team members' preferred tools
- Ideas failed to execute due to resource/scheduling constraints

Why Higgsfield:
- All-in-one integrated environment with leading generative models
- Quality of output was strongest differentiation
- Focus shifts from "which model" to "what video do we actually want to make"

Workflow:
- LLMs (Claude) flesh out ideas and design prompts
- Visualize in Higgsfield for rapid validation
- Finish final content by connecting to editing tools
- Planning, production, editing linked into one pipeline

Character consistency:
- Generate polished original character design using image model
- Fix character visuals as constant reference
- Generate series of videos assigning character to various actions/environments
- "Character lock" eliminates rework

Results:
- Production time ~1/10th
- Operating costs ~1/50th
- Character consistency maintained across 15M views channel
- Boosterz: cost -97%, time -79%, personnel -85%
- Scaling to more brands without proportional production burden

A shared workspace could let marketers and planners test prompts and visuals directly. Reusable locked characters would carry identity between those tests.

## 20. Case study distillation: Boxel Studio (Netflix/Hulu pre-production)
Profile: 350+ artists/producers/engineers, 16+ years M&E, titles for Netflix/A&E/Mattel/Cartoon Network/FX/Blumhouse/Hulu.

Before:
- Visual development (look exploration, early animation tests, lighting variations, iteration) required significant time/coordination.
- Bottlenecks pushed creative decisions later.
- Limited options presented to clients.
- Unnecessary downstream work when direction changed.

With Higgsfield Cinema Studio:
- Accelerated pre-production and look development while maintaining artistic control.
- Rapidly prototype environments, visualize sequences, explore alternate visual styles, accelerate look development.
- Faster ideation and early storytelling exploration when building concepts from scratch.
- Runs on same platform stack (Seedance 2.0, Kling 3.0, Veo 3.1) under one subscription.

Results:
- Time-to-visualization: months -> days
- Fewer iteration cycles, less downstream rework
- More creative options presented; stakeholders aligned earlier
- Higher output without quality compromise
- Artists shifted from technical bottlenecks to creative decision-making

IP/confidentiality:
- Uploaded data not used for model training
- Strict lifecycle management and permanent deletion protocols
- Enterprise framework met Hollywood client confidentiality standards

Human-centric AI:
- AI enhances, iterates, accelerates work originating from artists
- Does not replace creative process
- Human artists remain responsible for original designs, creative direction, final execution

Pre-production tests could measure time-to-visualization. Artists would retain creative direction, and enterprise work would require IP protections before production.

## 21. Case study distillation: Levector / Nestlé Tango ("Liberá tu cocodrilo")
Hybrid live + AI pipeline:
- Directed human performances provide movement/energy; AI transforms characters and surroundings.
- Live shoot in Quito; compositing, VFX, motion graphics, color in post.
- Performance defined by directing team first; AI transforms that performance (not vice versa).

Pre-production:
- Character exploration via Higgsfield: crocodile designs, character views, environments, movement tests.
- Rehearsal test: phone-recorded dancer paired with crocodile version to evaluate transformation before shoot.
- Models: GPT Image 2 + Seedance.

Cost/time:
- Saved ~3 weeks in character-development stages
- Character-concept/development ~half the time
- ~18,000-20,000 credits across image gen, tests, iterations, video gen
- Traditional alternative: >$6,000-7,000 for one lead character + motion across ~10 shots, before revisions/rendering/compositing

Role shift:
- Compositors help develop characters; editors explore environments; motion designers carry visual proposals into compositing.
- More parallel work; artists involved earlier in decisions shaping finished film.

A performance-led workflow could start with directed movement and a rehearsal test before the shoot. It would track cost per character and allow production roles to work in parallel.

## 22. Case study distillation: Fantasmagorie / Adopt Parfums ("Don't Touch My Mini")
Full-AI campaign (no live shoot):
- Concept: serial campaign (main film + shorter social pieces) instead of conventional announcement.
- Workflow: write/storyboard -> generate images/video in Higgsfield -> edit/sound/music in-house.
- Timeline: 3-4 weeks from writing to final delivery; no shoot days.
- Models: Nano Banana Pro, FLUX.2, GPT Image 2 for images; Seedance 2.0 for video; Canvas as working environment.
- Storyboards generated before shoot to explore compositions and show clients intended look; partially replaced reference moodboards.
- Result: 2M views in 48 hours without paid promotion.

Key insight: agency kept full creative control (concept, direction, visual language); AI expanded range of ideas testable before production constraints narrowed them.

A serial campaign could use generated storyboards to agree on direction with the client. Different models would share one Canvas, with sound and music completed in-house.

## 23. Case study distillation: Double Shots (music videos for pop idol Ivy)
Hybrid live + AI workflow:
- Certain scenes designated AI-generated from the start (not rescue in post).
- During shoot, crew photographed artist and key props specifically as source material for generated sequences, so generated shots carry same faces/wardrobe/objects.
- Post-production became exploration phase: at least one full week generating/refining material on Higgsfield; test several creative directions before locking final look.
- Selected generated shots cut into edit alongside live-action footage.

Tools:
- Nano Banana Pro for image generation
- Seedance 2.0 for video generation
- Topaz Labs upscaling/enhancement for selected outputs
- Claude for prompt development/refinement

Results:
- ~$1,500-2,000 AI generation per video
- Shots likely not attempted traditionally (additional VFX artists, drones, more set time, more post)
- Hand-drawn shot lists giving way to shot lists generated with Claude and produced on Higgsfield
- "Pitch the craziest idea we love — because we think we can produce it on Higgsfield"

Plan AI shots and capture continuity references during the shoot. Allow exploration before locking the look, and record cost per asset. The proposed tool chain uses Claude for prompts, Higgsfield for generation and Topaz for finishing.

## 24. Case study distillation: Gaia (streaming platform, AI animation at scale)
Workflow:
- Script → scenes; each scene pairs a voiceover block with a shot description.
- Prompts developed in Claude, sent into Higgsfield via MCP integration.
- Supercomputer for larger sequences: generate a full run of shots (e.g., 5 animations of 12s each in 20-30 min).
- Still imagery generated first and laid out on Premiere timeline; only after visual direction approved does animation begin.
- Sequence discipline: composition, subject, style resolved while static; motion generated last, after sign-off.

Results:
- Animation work: days/weeks -> hours (some tasks minutes)
- 3+ AI-heavy shows can run concurrently
- Traditional recreation cost: hundreds of thousands of dollars
- Recovered time reinvested into sophistication/quality, not just speed
- Enterprise: privacy/contractual protections before scale; bespoke agreement

Key insight: "Animation has run on that discipline for a century; the storyboard exists because motion is the most expensive place to change your mind. Gaia kept the discipline and changed the price."

Cost reality: prompt failure rate eats credits; prompting skill + QC remain essential.

The proposed plan would link script, scene and shot records with voiceover blocks. Claude prompts would reach Higgsfield through MCP, with Supercomputer handling batch shots. Approve stills before motion and settle enterprise privacy requirements before execution.

## 25. Case study distillation: Kerri Zane Enterprises (Emmy producer, AI pipeline)
Workflow before Higgsfield:
- Single shot passed through 3-4 platforms before anyone knew if it worked in motion.
- Concepts/treatments -> shot lists/mood boards -> hero frames -> separate motion/enhancement tools -> editing stack.
- Slow at the exact moment speed mattered most: client alignment.

Core idea:
- AI makes creating options fast, but avalanche of options is not direction.
- Change what client sees first: show how scene might actually feel, with motion in conversation from day one.
- Every weak direction killed in first meeting is one that won't consume production time.
- Goal: get to right idea quickly with something concrete enough to react to.

With Higgsfield Cinema Studio:
- Production instrument for visual development, previs, first-pass shot creation; sits inside existing stack.
- Camera controls: test slow push-in, tracking, handheld, aggressive moves without rebuilding concept.
- Image-to-video turns approved hero frames into moving shots.
- Frame-based control anchors start/end.
- Multiple visual treatments of same idea in parallel; real choices to client within working day.

Results:
- 25-40% reduction in concept/pre-production time (1-2 working days on short-form)
- 30-50% reduction in early visualization/concept-development costs
- Meaningful moving concepts in hours; client-ready visual direction same day; 24-72 hours for larger sequence first pass
- Feature film test: 24-hour brief completed in under 8 hours
- Team keeps 2-3 projects moving at once; more considered options without more chaos

Moving concepts could help clients choose between parallel treatments. The plan would expose camera controls and measure time-to-first-moving-concept.

## 26. Case study distillation: One of One (Maradona official brand world)
AI-native studio built around talent/IP and AI rights to likeness.

Workflow:
- Creative development: use image generation to visualize concepts early; build brand world as visual storyboard, not just written idea.
- Lock direction with client before full execution; agree on what must remain true to the person (look, move, feel) as rulebook.
- Execution: model routing matters; pick right model for stills vs video; stay on platform through final delivery (upscaling, sound, assembly).
- Toolset: Nano Banana Pro/2 + Cinema Studio for image/editorial/e-commerce consistency; Seedance 2.0 + Kling v3.0 for campaign films/animation.

Key insights:
- Stills quality conversation is "over"; video is on same curve but earlier.
- Clients at top level can distinguish magic vs craft; discipline of only shipping when standard met builds trust.
- Platform as orchestra: individual models are instruments; platform gives all instruments in one place; studio is composer/conductor (taste/craft).
- Adopt tools fast, but energy should go into becoming better conductor; when everyone has same orchestra, differentiation is what you do with it.
- Weeks instead of months; lean team takes on ambitious world-building projects.

The proposed workflow would record model routing, reuse approved likeness assets and agree on a visual storyboard before execution. Delivery would still require the studio's quality review and creative judgement.

## 27. Cross-case workflow patterns (synthesis)
Common patterns across 13 case studies:

1. Planning-first: intent → shot contract → model routing → generation → review (PURGA, Vertex, Gaia, Sinecera, One of One).
2. Character-first: lock identity/visual direction before world-building (PURGA, Sinecera, AdQUA, Double Shots).
3. Reference-as-specification: group references by function; describe role in prompt; Canvas as reference board (Big Purple, Canvas docs).
4. Hybrid VFX: plate → generative pass → compositing → finishing; generation does hours, craft makes it hold up (BITT, Levector).
5. Performance-first: direct real movement, then transform; rehearsal test before shoot (Levector).
6. Keyframe-first: approved still → motion; text-to-video is exception (Sinecera).
7. Multi-shot from approved frames: Multishot turns approved storyboard frames into moving shots across models (Sinecera).
8. Resolution ladder: 720p for iteration, 1080p/4K for final (Vertex, Double Shots).
9. Model routing by shot need: realism (Kling), cinematic audio (Veo), product (Seedance), fast (Hailuo/Turbo), stylized (Wan).
10. Native audio models reduce post-production (Veo, Seedance, Kling).
11. Async job polling + status tracking in adapter; retries and idempotency.
12. Credit/cost estimation in preflight; prompt failure rate eats credits.
13. Canvas node graph: prompt → image → video → edit, typed connections, fan-out; references by function; describe role in prompt.
14. Approval gates per stage: boards → previz → offline → online (Sinecera).
15. Motion-first client alignment: show moving concepts early to kill weak directions (Kerri Zane).
16. Pre-production visualization acceleration: months → days (Boxel).
17. Enterprise IP protection as hard gate (Boxel, Gaia).
18. Human-centric AI: AI enhances/accelerates; artists own creative direction (Boxel).
19. Revision granularity: precise adjustments without restarting scenes (Big Purple "Revision-Proof").
20. Full-AI serial campaigns: no shoot days; 3-4 weeks writing to delivery (Adopt).
21. All-in-one reduces tool sprawl; character lock as reusable asset (AdQUA).
22. LLM prompt design + visual validation loop; marketers/planners can experiment directly (AdQUA).
23. AI shots planned from start, not rescue; capture source material on set (Double Shots).
24. Exploration phase before lock; cost transparency per asset (Double Shots).
25. Script → scene → shot with voiceover blocks; Claude prompts via MCP; Supercomputer batch (Gaia).
26. Stills-first approval before motion; motion is most expensive place to change mind (Gaia).
27. Model routing as first-class; talent likeness as reusable asset; visual storyboard before execution (One of One).
28. Quality standard gate: only ship when standard met; taste as differentiator (One of One).
29. Platform as orchestra; studio as composer/conductor (One of One).
30. Time-to-visualization and time-to-first-moving-concept as key metrics.

These patterns map directly to aigc-agent-studio's compiler/gate/adapter design.
