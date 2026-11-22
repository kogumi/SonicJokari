// =====================================================================
//  Sonic Jokari — moteur son SuperCollider
//  Piloté en OSC par jokari.py (port sclang 57120, réponses vers 57130)
//  Attention : en SuperCollider, a + b * c = (a + b) * c  -> parenthèses partout.
// =====================================================================
(
var py = NetAddr("127.0.0.1", 57130);
var bufs = Dictionary.new;
var srcGroup, fxGroup, revBus, reverb, master, ball, arp, sabers, victory;
var beatOn = 0, beatLvl = 0, beatVol = 0.6, beatBpm = 140, beatN = [0, 0, 0], beatStep = 0, beatRR = [0, 0, 0], beatPlay;
var fxNames = [\impact, \mur, \elastique, \faute, \point, \service, \victoire, \trinque, \parfait, \riser];

s = Server.default;
// sortie audio choisie par le jeu (JOKARI_OUT) ; entrée forcée sur un micro qui n'est pas
// Bluetooth (JOKARI_IN) : ouvrir le micro d'une enceinte Bluetooth la ferait passer en mode
// « kit mains libres » (mono 16 kHz). Le jeu n'utilise pas d'entrée audio.
if("JOKARI_OUT".getenv.notNil and: { "JOKARI_OUT".getenv.size > 0 }) { s.options.outDevice = "JOKARI_OUT".getenv };
if("JOKARI_IN".getenv.notNil and: { "JOKARI_IN".getenv.size > 0 }) { s.options.inDevice = "JOKARI_IN".getenv };
s.options.numOutputBusChannels = 2;
s.options.numInputBusChannels = 0;
s.options.memSize = 65536;
s.options.hardwareBufferSize = 256;

s.waitForBoot {

	// ---------------- Balle : « voiture de science-fiction » ----------------
	SynthDef(\jk_ball, { |out = 0, revBus, amp = 0, freq = 90, ratio = 1, cutoff = 3000, rev = 0.2,
		tension = 0, speed = 0, pan = 0, detune = 0.4, fm = 1.2, grit = 0.3, wobble = 5,
		volume = 0.6, tensionBoost = 1, combo = 0, energy = 0.5, low = -7, rise = 19, epitch = 12, evar = 1, cue = 0, cueVol = 0.6, approach = 0, noiseVol = 0.5, dub = 0, bpm = 140|
		var a, f, t, sp, c, e, wob, lfo, mod, sig, g1, g2, g4, layers, k, cueSig, ap, pump, rate, nz, wl, dz;
		a = amp.lag(0.06);
		t = tension.lag(0.1) * tensionBoost;
		sp = speed.lag(0.1);
		c = combo.lag(0.8);
		// le combo fait glisser la balle du grave vers l'aigu (low -> low + rise demi-tons)
		e = energy.lag(0.05);   // force de la frappe, gardée tout le vol
		// variation : modulations aléatoires de hauteur et de filtre, d'autant plus fortes que la frappe l'est
		wob = LFNoise1.kr(1.5 + (e * 7)) * (e.clip(0, 1.3) ** 2) * evar;
		// hauteur : combo (grave -> aigu) + force de frappe (douce = plus grave, forte = plus aiguë)
		f = (freq * ratio.lag(0.04) * (2 ** ((low + (c.clip(0, 1) * rise) + (epitch * (e.clip(0, 1.3) - 0.5))) / 12))
			* (1 + (wob * 0.035))).clip(20, 8000);
		// dubstep : wobble du filtre calé sur le tempo ; noires -> croches -> triolets -> doubles avec le combo
		dz = dub.lag(0.3).clip(0, 1.5);
		wl = (LFTri.kr((bpm / 60) * Select.kr((c.clip(0, 0.999) * 4).floor, [1, 2, 3, 4])) * 0.5) + 0.5;
		// moteur : modulation d'amplitude qui s'accélère avec la vitesse, la tension et le combo
		lfo = SinOsc.kr(wobble * (0.6 + (e * 0.8) + (sp * 0.8) + (t * 3) + (c * 2))).range(1 - ((0.2 + (0.3 * e)) * (1 + t)).min(0.9), 1);
		mod = SinOsc.ar(f * 0.5) * f * fm * (1 + t) * (0.3 + (sp * 0.6) + (e * 0.8)) * (1 + (dz * wl * 1.5));
		sig = (Mix(Saw.ar(f * [1, 1 + (detune * 0.01 * (0.4 + e)), 1 - (detune * 0.01 * (0.4 + e))])) * 0.25)
		    + (Pulse.ar(f * 0.5, 0.3) * 0.2)
		    + (SinOsc.ar(f + mod) * 0.3);
		// vitesse : balle lente = ronde et sourde, balle rapide = brillante et granuleuse
		sig = (sig * (1 + (grit * 6 * (0.1 + t + (sp * 0.5) + (e * 0.5))))).tanh;
		sig = RLPF.ar(sig, (cutoff.lag(0.05) * (1 + t) * (0.45 + (sp * 1.1)) * (1 + (wob * 0.6))
			* ((1 - dz.clip(0, 1)) + (dz * (0.12 + (2.2 * (wl ** 2)))))).clip(60, 16000), 0.35);

		// couches du combo, qui entrent l'une après l'autre
		g1 = ((c - 0.15) / 0.15).clip(0, 1);   // sub qui pulse
		g2 = ((c - 0.35) / 0.15).clip(0, 1);   // supersaw une quinte au-dessus
		g4 = ((c - 0.85) / 0.15).clip(0, 1);   // turbine de bruit
		layers = (SinOsc.ar(f * 0.5) * LFPulse.kr(wobble * 2 * (1 + sp), 0, 0.6).lag(0.01) * 0.5 * g1)
		    + (RLPF.ar(Mix(Saw.ar(f * 1.5 * [1, 1.006, 0.994, 1.012, 0.988])) * 0.09,
		        (f * 6 * (1 + t)).clip(100, 14000), 0.3) * g2)
		    + (BPF.ar(PinkNoise.ar, (f * 8 * (1 + sp)).clip(100, 12000), 0.4) * 0.9 * g4);
		sig = sig + (layers.tanh * (1 + t));
		// retour : souffle de bruit « pompé » (effet shaper) dont les pulsations accélèrent à l'approche
		ap = approach.lag(0.05);
		rate = 2 + ((ap ** 1.5) * 26 * (0.5 + (e * 0.7)));
		pump = (1 - LFSaw.kr(rate, 1).range(0, 1)) ** 3;
		nz = BPF.ar(WhiteNoise.ar ! 2, (cutoff.lag(0.05) * (0.6 + (ap * 1.5))).clip(150, 14000), 0.6 - (ap * 0.35));
		nz = (nz * (2 + (e * 4))).tanh * pump * (ap > 0.001).lag(0.1) * (ap ** 0.7) * noiseVol * 0.5;
		// indicatif : la balle se double à l'octave juste avant d'arriver, et culmine au bon moment
		k = cue.lag(0.03);
		cueSig = (SinOsc.ar(f * 2) + (LFTri.ar(f * 4.003) * 0.35) + (Pulse.ar(f * 2.002, 0.25) * 0.12))
			* SinOsc.kr(8 + (k * 14)).range(0.7, 1);
		sig = sig + (RLPF.ar(cueSig, (f * 8 * (0.5 + k)).clip(200, 14000), 0.4) * (k ** 2) * cueVol * 0.6);
		sig = sig * lfo * a * volume * (0.55 + (e * 0.7)) * (1 + (c * 0.5));
		sig = Pan2.ar(sig, pan.lag(0.05));
		sig = sig + (Balance2.ar(nz[0], nz[1], pan.lag(0.05) * 0.7) * lfo * a * volume);
		Out.ar(out, sig);
		Out.ar(revBus, sig * rev.lag(0.1));
	}).add;

	// ---------------- Sabre : bourdon de chaque manette ----------------
	SynthDef(\jk_saber, { |out = 0, revBus, on = 0, freq = 70, pan = 0, motion = 0, volume = 0.35,
		bright = 1, buzz = 0.5, idle = 0.2, rev = 0.15|
		var m, f, sig, env;
		m = Lag2.kr(motion, 0.04).clip(0, 1.5);
		f = freq * (1 + (m * 0.12));
		sig = (Mix(Saw.ar(f * [1, 1.007, 2.01])) * 0.15) + (SinOsc.ar(f * 0.5) * 0.35);
		sig = sig + (BPF.ar(WhiteNoise.ar, f * 6, 0.5) * buzz * m * 0.6);
		sig = RLPF.ar(sig, (250 + (m * 5000 * bright)).clip(80, 14000), 0.25);
		sig = (sig * 1.5).tanh;
		env = (idle + (m * (1 - idle))).clip(0, 1.2) * on.lag(0.3) * volume;
		sig = Pan2.ar(sig * env, pan.lag(0.1));
		Out.ar(out, sig);
		Out.ar(revBus, sig * rev);
	}).add;

	// ---------------- Lecteur de samples (impacts, mur, etc.) ----------------
	SynthDef(\jk_sample, { |out = 0, revBus, buf, rate = 1, amp = 0.8, pan = 0, cutoff = 18000, rev = 0.1|
		var sig = PlayBuf.ar(1, buf, rate * BufRateScale.kr(buf), doneAction: 2);
		sig = LPF.ar(sig, cutoff.clip(100, 19000));
		sig = Pan2.ar(sig * amp, pan);
		Out.ar(out, sig);
		Out.ar(revBus, sig * rev);
	}).add;

	// ---------------- Sons de secours synthétisés (si pas de sample) ----------------
	SynthDef(\jk_fx_impact, { |out = 0, revBus, rate = 1, amp = 0.8, pan = 0, cutoff = 18000, rev = 0.1|
		var env = EnvGen.ar(Env.perc(0.001, 0.3), doneAction: 2);
		var body = SinOsc.ar(XLine.ar(420 * rate, 110 * rate, 0.08)) * EnvGen.ar(Env.perc(0.001, 0.12));
		var click = HPF.ar(WhiteNoise.ar, 2500) * EnvGen.ar(Env.perc(0.0005, 0.02));
		var ring = Ringz.ar(Impulse.ar(0), [930, 1470, 2290] * rate, [0.12, 0.08, 0.05]).sum * 0.04;
		var sig = ((body * 0.8) + (click * 0.5) + ring) * env;
		sig = Pan2.ar(LPF.ar(sig, cutoff.clip(100, 19000)) * amp, pan);
		Out.ar(out, sig); Out.ar(revBus, sig * rev);
	}).add;

	SynthDef(\jk_fx_mur, { |out = 0, revBus, rate = 1, amp = 0.8, pan = 0, cutoff = 18000, rev = 0.5|
		var env = EnvGen.ar(Env.perc(0.002, 0.6), doneAction: 2);
		var thud = SinOsc.ar(XLine.ar(160 * rate, 50 * rate, 0.15)) * EnvGen.ar(Env.perc(0.002, 0.25));
		var slap = Ringz.ar(Impulse.ar(0), [190, 280, 430, 610] * rate, 0.25).sum * 0.03;
		var noise = LPF.ar(WhiteNoise.ar, 1800) * EnvGen.ar(Env.perc(0.001, 0.06));
		var sig = ((thud * 0.9) + slap + (noise * 0.4)) * env;
		sig = Pan2.ar(LPF.ar(sig, cutoff.clip(100, 19000)) * amp, pan);
		Out.ar(out, sig); Out.ar(revBus, sig * rev);
	}).add;

	SynthDef(\jk_fx_elastique, { |out = 0, revBus, rate = 1, amp = 0.8, pan = 0, cutoff = 18000, rev = 0.4|
		var env = EnvGen.ar(Env.perc(0.01, 0.7), doneAction: 2);
		var f = 140 * rate * (1 + (SinOsc.kr(13) * 0.25 * env));
		var sig = (SinOsc.ar(f) + (Saw.ar(f * 2) * 0.15)) * env * 0.6;
		sig = Pan2.ar(LPF.ar(sig, cutoff.clip(100, 19000)) * amp, pan);
		Out.ar(out, sig); Out.ar(revBus, sig * rev);
	}).add;

	SynthDef(\jk_fx_faute, { |out = 0, revBus, rate = 1, amp = 0.8, pan = 0, cutoff = 18000, rev = 0.2|
		var env = EnvGen.ar(Env.perc(0.01, 1.0), doneAction: 2);
		var f = XLine.ar(500 * rate, 50 * rate, 0.9);
		var sig = RLPF.ar(Mix(Saw.ar(f * [1, 1.01])), (f * 4).clip(80, 12000), 0.3) * env * 0.4;
		sig = Pan2.ar(LPF.ar(sig, cutoff.clip(100, 19000)) * amp, pan);
		Out.ar(out, sig); Out.ar(revBus, sig * rev);
	}).add;

	SynthDef(\jk_fx_point, { |out = 0, revBus, rate = 1, amp = 0.8, pan = 0, cutoff = 18000, rev = 0.2|
		var timer = Line.kr(0, 0, 1.2, doneAction: 2);
		var n1 = SinOsc.ar(660 * rate) * EnvGen.ar(Env.perc(0.005, 0.3));
		var n2 = DelayN.ar(SinOsc.ar(990 * rate) * EnvGen.ar(Env.perc(0.005, 0.5)), 0.3, 0.15);
		var sig = ((n1 + n2) * 0.3) + (timer * 0);
		sig = Pan2.ar(LPF.ar(sig, cutoff.clip(100, 19000)) * amp, pan);
		Out.ar(out, sig); Out.ar(revBus, sig * rev);
	}).add;

	SynthDef(\jk_fx_service, { |out = 0, revBus, rate = 1, amp = 0.5, pan = 0, cutoff = 18000, rev = 0.2|
		var env = EnvGen.ar(Env.new([0, 1, 0], [0.35, 0.4], [2, -4]), doneAction: 2);
		var sweep = BPF.ar(WhiteNoise.ar, XLine.ar(300 * rate, 3000 * rate, 0.6), 0.3) * 1.5;
		var bell = SinOsc.ar(1320 * rate) * EnvGen.ar(Env.perc(0.005, 0.4)) * 0.25;
		var sig = (sweep + bell) * env * 0.5;
		sig = Pan2.ar(LPF.ar(sig, cutoff.clip(100, 19000)) * amp, pan);
		Out.ar(out, sig); Out.ar(revBus, sig * rev);
	}).add;

	SynthDef(\jk_fx_victoire, { |out = 0, revBus, rate = 1, amp = 0.8, pan = 0, cutoff = 18000, rev = 0.3|
		var timer = Line.kr(0, 0, 2.0, doneAction: 2);
		var sig = Mix.fill(4, { |i|
			var f = [523.25, 659.25, 783.99, 1046.5][i] * rate;
			DelayN.ar(Pulse.ar(f, 0.3) * EnvGen.ar(Env.perc(0.01, 0.7)), 1, i * 0.13)
		}) * 0.15;
		sig = Pan2.ar(LPF.ar(sig, cutoff.clip(100, 19000)) * amp, pan) + (timer * 0);
		Out.ar(out, sig); Out.ar(revBus, sig * rev);
	}).add;

	SynthDef(\jk_fx_trinque, { |out = 0, revBus, rate = 1, amp = 0.8, pan = 0, cutoff = 18000, rev = 0.3|
		var env = EnvGen.ar(Env.perc(0.0005, 1.2), doneAction: 2);
		var sig = Ringz.ar(Impulse.ar(0) * 0.3, [2093, 3378, 5120, 6870] * rate, [1.0, 0.6, 0.35, 0.2]).sum;
		sig = (sig * 0.06 * env).tanh;
		sig = Pan2.ar(LPF.ar(sig, cutoff.clip(100, 19000)) * amp, pan);
		Out.ar(out, sig); Out.ar(revBus, sig * rev);
	}).add;

	// Frappe parfaite : coup de sub + « zap » qui monte, comme un turbo qui s'enclenche
	SynthDef(\jk_fx_parfait, { |out = 0, revBus, rate = 1, amp = 0.8, pan = 0, cutoff = 18000, rev = 0.3|
		var env = EnvGen.ar(Env.perc(0.002, 0.9), doneAction: 2);
		var sub = SinOsc.ar(XLine.ar(110 * rate, 38 * rate, 0.25)) * EnvGen.ar(Env.perc(0.002, 0.35)) * 0.9;
		var f = XLine.ar(300 * rate, 2400 * rate, 0.35);
		var zap = Mix(Saw.ar(f * [1, 1.005, 0.497])) * EnvGen.ar(Env.perc(0.01, 0.6)) * 0.12;
		var sig = (sub + RLPF.ar(zap, (f * 3).clip(80, 16000), 0.2)) * env;
		sig = (sig * 1.6).tanh;
		sig = Pan2.ar(LPF.ar(sig, cutoff.clip(100, 19000)) * amp, pan);
		Out.ar(out, sig); Out.ar(revBus, sig * rev);
	}).add;

	// Riser : monte pendant tout le retour de la balle et culmine à son arrivée (dur = durée)
	SynthDef(\jk_fx_riser, { |out = 0, revBus, rate = 1, amp = 0.8, pan = 0, cutoff = 18000, rev = 0.35, dur = 2|
		var env = EnvGen.ar(Env.new([0, 1, 0], [dur, 0.06], [4, -4]), doneAction: 2);
		var prog = Line.kr(0, 1, dur);
		var f = 90 * rate * (2 ** (prog * 3));
		var trem = SinOsc.kr(3 + (prog * 22)).range(0.55, 1);
		var noise = BPF.ar(WhiteNoise.ar, (f * 10).clip(100, 15000), 0.25) * 1.4;
		var saw = RLPF.ar(Mix(Saw.ar(f * [1, 1.012, 0.5, 1.5])) * 0.1, (f * 5).clip(100, 16000), 0.25);
		var sig = (noise + saw) * env * trem;
		sig = Pan2.ar(LPF.ar(sig, cutoff.clip(100, 19000)) * amp, pan);
		Out.ar(out, sig); Out.ar(revBus, sig * rev);
	}).add;

	// ---------------- Arpégiateur : entre à un certain niveau de combo ----------------
	// Notes accordées sur la balle (elles montent avec elle), tempo qui s'accélère avec le combo,
	// la vitesse et la tension ; notes pincées, filtre ouvert par la force, ping-pong gauche/droite.
	SynthDef(\jk_arp, { |out = 0, revBus, amp = 0, freq = 90, ratio = 1, combo = 0, speed = 0, tension = 0,
		pan = 0, energy = 0.5, low = -7, rise = 19, volume = 0.5, threshold = 0.35, rate = 5, octave = 1,
		motif = 0, rev = 0.3, epitch = 12|
		var c = combo.lag(0.8);
		var gate = ((c - threshold) / 0.1).clip(0, 1);
		var tempo = (rate * (1 + c) * (1 + (speed.lag(0.2) * 0.5)) * (1 + tension.lag(0.1))).clip(1, 40);
		var trig = Impulse.kr(tempo);
		var seqs = [
			Dseq([0, 3, 7, 10, 12, 15, 19, 22, 24, 22, 19, 15, 12, 10, 7, 3], inf),   // mineur
			Dseq([0, 4, 7, 11, 12, 16, 19, 23, 24, 23, 19, 16, 12, 11, 7, 4], inf),   // majeur
			Dseq([0, 7, 12, 19, 24, 19, 12, 7], inf),                                 // quintes
			Drand([0, 3, 7, 10, 12, 15, 19, 24], inf)                                 // aléatoire
		];
		var note = Demand.kr(trig, 0, Dswitch1(seqs, motif.round.clip(0, 3)));
		var base = freq * ratio.lag(0.04) * (2 ** ((low + (c.clip(0, 1) * rise) + (epitch * (energy.lag(0.05).clip(0, 1.3) - 0.5))) / 12))
			* (2 ** octave.round);
		var f = (base * (2 ** (note / 12))).clip(40, 9000);
		var env = Decay2.kr(trig, 0.003, (0.7 / tempo).clip(0.03, 0.35));
		var sig = Pulse.ar(f, 0.3) + (Saw.ar(f * 1.005) * 0.5);
		var side = (ToggleFF.kr(trig) * 2) - 1;
		sig = RLPF.ar(sig, (f * (1.5 + (env * 6) + (energy * 3))).clip(100, 15000), 0.25) * env;
		sig = sig * 0.22 * ((amp.lag(0.06) * 0.6) + 0.4) * (amp > 0.001).lag(0.2) * volume * gate;
		sig = Pan2.ar(sig, (pan.lag(0.05) + (side * 0.35)).clip(-1, 1));
		Out.ar(out, sig);
		Out.ar(revBus, sig * rev);
	}).add;

	// ---------------- Musique de victoire (si aucun sample n'est choisi pour « victoire ») ----------------
	SynthDef(\jk_vlead, { |out = 0, revBus, freq = 440, dur = 0.3, amp = 0.2, pan = 0, rev = 0.25|
		var env = EnvGen.ar(Env.linen(0.008, dur, 0.18, 1, -3), doneAction: 2);
		var sig = Mix(Saw.ar(freq * [1, 1.004, 0.996])) * 0.3 + (Pulse.ar(freq * 2, 0.3) * 0.12);
		sig = RLPF.ar(sig, (freq * (3 + (EnvGen.kr(Env.perc(0.01, dur)) * 6))).clip(200, 15000), 0.3) * env;
		sig = Pan2.ar(sig * amp, pan);
		Out.ar(out, sig); Out.ar(revBus, sig * rev);
	}).add;
	SynthDef(\jk_vpad, { |out = 0, revBus, freq = 220, dur = 1, amp = 0.1, pan = 0, rev = 0.4|
		var env = EnvGen.ar(Env.linen(0.04, dur, 0.5, 1, -2), doneAction: 2);
		var sig = LPF.ar(Mix(Saw.ar(freq * [1, 1.006, 0.994, 2.003])) * 0.2, 2200) * env;
		sig = Pan2.ar(sig * amp, pan);
		Out.ar(out, sig); Out.ar(revBus, sig * rev);
	}).add;
	SynthDef(\jk_vpluck, { |out = 0, revBus, freq = 880, amp = 0.1, pan = 0, rev = 0.3|
		var env = EnvGen.ar(Env.perc(0.002, 0.22), doneAction: 2);
		var sig = RLPF.ar(Pulse.ar(freq, 0.35), (freq * 4 * env + 300).clip(200, 15000), 0.3) * env;
		sig = Pan2.ar(sig * amp, pan);
		Out.ar(out, sig); Out.ar(revBus, sig * rev);
	}).add;
	SynthDef(\jk_vbass, { |out = 0, freq = 55, dur = 0.4, amp = 0.3|
		var env = EnvGen.ar(Env.perc(0.005, dur), doneAction: 2);
		var sig = (SinOsc.ar(freq) + (LPF.ar(Pulse.ar(freq, 0.4), freq * 4) * 0.4)) * env;
		Out.ar(out, Pan2.ar(sig * amp, 0));
	}).add;
	SynthDef(\jk_vkick, { |out = 0, amp = 0.5|
		var env = EnvGen.ar(Env.perc(0.001, 0.35), doneAction: 2);
		var sig = SinOsc.ar(XLine.ar(160, 45, 0.12)) * env;
		Out.ar(out, Pan2.ar((sig * 1.5).tanh * amp, 0));
	}).add;
	SynthDef(\jk_vsnare, { |out = 0, revBus, amp = 0.3, rev = 0.25|
		var env = EnvGen.ar(Env.perc(0.001, 0.18), doneAction: 2);
		var sig = ((BPF.ar(WhiteNoise.ar, 3000, 0.8) * 1.5) + (SinOsc.ar(185) * EnvGen.ar(Env.perc(0.001, 0.06)))) * env;
		sig = Pan2.ar(sig * amp, 0);
		Out.ar(out, sig); Out.ar(revBus, sig * rev);
	}).add;

	SynthDef(\jk_vhat, { |out = 0, amp = 0.2, pan = 0, rate = 1|
		var env = EnvGen.ar(Env.perc(0.001, 0.05 * rate), doneAction: 2);
		var sig = HPF.ar(WhiteNoise.ar, 7000 * rate.clip(0.5, 2)) * env;
		Out.ar(out, Pan2.ar(sig * amp, pan));
	}).add;

	// Petit morceau (≈ 5 s, 132 bpm) : fanfare sur I – vi – IV – V – I, accords, basse, arpège, batterie.
	victory = { |rate = 1, amp = 0.8, pan = 0|
		var beat = 60 / 132, root = 60.midicps * rate.clip(0.7, 1.4), lv = amp.clip(0, 2);
		var nf = { |semi| root * (2 ** (semi / 12)) };
		var chords = [[0, 4, 7], [-3, 0, 4], [-7, -3, 0], [-5, -1, 2], [0, 4, 7]];
		var lead = [[7, 0.5], [7, 0.25], [12, 1.25], [9, 0.5], [12, 0.5], [16, 1], [12, 0.5], [9, 0.5], [5, 1],
			[7, 0.5], [11, 0.5], [14, 1], [12, 0.5], [16, 0.5], [19, 3]];
		fork {                                                     // accompagnement
			chords.do { |ch, i|
				var beats = if(i == 4) { 4 } { 2 };
				ch.do { |n, j| Synth(\jk_vpad, [\out, 0, \revBus, revBus, \freq, nf.(n), \dur, beats * beat,
					\amp, 0.09 * lv, \pan, (j - 1) * 0.5], srcGroup) };
				Synth(\jk_vbass, [\out, 0, \freq, nf.(ch[0] - 24), \dur, beat * 0.9, \amp, 0.35 * lv], srcGroup);
				(beats * 2).do { |q|                               // croches : arpège + batterie
					var n = ch[q % 3] + (12 * ((q div: 3) % 2)) + 12;
					Synth(\jk_vpluck, [\out, 0, \revBus, revBus, \freq, nf.(n), \amp, 0.07 * lv,
						\pan, if(q.even) { -0.4 } { 0.4 }], srcGroup);
					if(q.even) { Synth(\jk_vkick, [\out, 0, \amp, 0.45 * lv], srcGroup) };
					if((q % 4) == 2) { Synth(\jk_vsnare, [\out, 0, \revBus, revBus, \amp, 0.25 * lv], srcGroup) };
					if((q == 2) and: { i < 4 }) {
						Synth(\jk_vbass, [\out, 0, \freq, nf.(ch[0] - 24), \dur, beat * 0.9, \amp, 0.3 * lv], srcGroup) };
					(beat / 2).wait;
				};
			};
		};
		fork {                                                     // mélodie de fanfare
			lead.do { |n|
				Synth(\jk_vlead, [\out, 0, \revBus, revBus, \freq, nf.(n[0] + 12), \dur, n[1] * beat * 0.85,
					\amp, 0.16 * lv, \pan, pan * 0.5], srcGroup);
				(n[1] * beat).wait;
			};
		};
	};

	// ---------------- Réverb + limiteur ----------------
	SynthDef(\jk_reverb, { |in, out = 0, room = 0.85, damp = 0.4|
		var sig = In.ar(in, 2);
		Out.ar(out, FreeVerb2.ar(sig[0], sig[1], 1, room, damp));
	}).add;

	SynthDef(\jk_master, { |gain = 0.9|
		var sig = In.ar(0, 2) * gain;
		ReplaceOut.ar(0, Limiter.ar(sig, 0.95, 0.01));
	}).add;

	s.sync;

	revBus = Bus.audio(s, 2);
	srcGroup = Group.head(s);
	fxGroup = Group.after(srcGroup);
	reverb = Synth(\jk_reverb, [\in, revBus, \out, 0], fxGroup);
	master = Synth.tail(s, \jk_master);
	ball = Synth(\jk_ball, [\out, 0, \revBus, revBus], srcGroup);
	arp = Synth(\jk_arp, [\out, 0, \revBus, revBus], srcGroup);
	sabers = 8.collect { Synth(\jk_saber, [\out, 0, \revBus, revBus, \on, 0], srcGroup) };

	// ---------------- OSC ----------------
	OSCdef(\jkHello, { py.sendMsg('/jokari/ready') }, '/jokari/hello');

	// /ball amp ratio cutoff rev tension speed pan combo energy cue approach
	OSCdef(\jkBall, { |m|
		ball.set(\amp, m[1], \ratio, m[2], \cutoff, m[3], \rev, m[4], \tension, m[5], \speed, m[6], \pan, m[7],
			\combo, m[8] ? 0, \energy, m[9] ? 0.5, \cue, m[10] ? 0, \approach, m[11] ? 0);
		arp.set(\amp, m[1], \ratio, m[2], \tension, m[5], \speed, m[6], \pan, m[7],
			\combo, m[8] ? 0, \energy, m[9] ? 0.5);
	}, '/ball');

	// /set cible clé valeur clé valeur ...
	OSCdef(\jkSet, { |m|
		var pairs = m[2..];
		switch(m[1],
			\ball, { ball.set(*pairs) },
			\arp, { arp.set(*pairs) },
			\saber, { sabers.do { |x| x.set(*pairs) } },
			\reverb, { reverb.set(*pairs) },
			\master, { master.set(*pairs) }
		);
	}, '/set');

	// /saber index on freq pan
	OSCdef(\jkSaber, { |m|
		var i = m[1].asInteger;
		if(i < sabers.size) { sabers[i].set(\on, m[2], \freq, m[3], \pan, m[4]) };
	}, '/saber');

	// /motion m0 m1 ...
	OSCdef(\jkMotion, { |m|
		m[1..].do { |v, i| if(i < sabers.size) { sabers[i].set(\motion, v) } };
	}, '/motion');

	// /load type chemin   (chemin vide -> synthé intégré)
	OSCdef(\jkLoad, { |m|
		var kind = m[1].asSymbol, path = m[2].asString, old = bufs[kind];
		if(path.size == 0) {
			bufs[kind] = nil; if(old.notNil) { old.free };
		} {
			Buffer.readChannel(s, path, channels: [0], action: { |b|
				bufs[kind] = b;
				if(old.notNil) { old.free };
				("Jokari : sample chargé pour " ++ kind ++ " -> " ++ path).postln;
			});
		};
	}, '/load');

	// /play type rate amp pan cutoff rev [dur]
	OSCdef(\jkPlay, { |m|
		var kind = m[1].asSymbol, b = bufs[kind], dur = (m[7] ? 0).max(0);
		var base = m[1].asString.split($#)[0].asSymbol;   // « impact#j0#2 » -> impact
		var args = [\out, 0, \revBus, revBus, \rate, m[2], \amp, m[3], \pan, m[4], \cutoff, m[5], \rev, m[6],
			\dur, dur.max(0.3)];
		if(b.notNil) {
			// sample de riser : étiré ou compressé pour finir pile à l'arrivée de la balle
			if((base == \riser) and: { dur > 0 }) { args[5] = m[2] * (b.duration / dur).clip(0.5, 2) };
			Synth(\jk_sample, args ++ [\buf, b], srcGroup);
		} {
			if(base == \victoire) { victory.(m[2], m[3], m[4]) } {
				if(fxNames.includes(base)) { Synth(("jk_fx_" ++ base).asSymbol, args, srcGroup) };
			};
		};
	}, '/play');

	// ---------------- Beat dubstep (demi-tempo), joué avec les samples du kit ----------------
	// grosse caisse sur le 1, caisse claire sur le 3 ; le combo ajoute charleys, contretemps et doubles
	OSCdef(\jkBeatKit, { |m| beatN = [m[1], m[2], m[3]].collect { |x| (x ? 0).asInteger } }, '/beatkit');
	OSCdef(\jkBeat, { |m| beatOn = m[1]; beatLvl = m[2]; beatVol = m[3]; beatBpm = m[4] }, '/beat');
	beatPlay = { |part, idx, amp, rate = 1, pan = 0|
		var n = beatN[idx], b;
		if(n > 0) {                                    // samples du kit
			b = bufs[("beat_" ++ part ++ "#" ++ (beatRR[idx] % n)).asSymbol];
			beatRR[idx] = beatRR[idx] + 1;
			if(b.notNil) { Synth(\jk_sample, [\out, 0, \revBus, revBus, \buf, b, \rate, rate, \amp, amp,
				\pan, pan, \rev, 0.08], srcGroup) };
		} {                                            // sinon batterie synthétisée
			switch(part,
				\kick, { Synth(\jk_vkick, [\out, 0, \amp, amp * 0.6], srcGroup) },
				\snare, { Synth(\jk_vsnare, [\out, 0, \revBus, revBus, \amp, amp * 0.4], srcGroup) },
				\hat, { Synth(\jk_vhat, [\out, 0, \amp, amp * 0.5, \pan, pan, \rate, rate], srcGroup) }
			);
		};
	};
	Routine({
		loop {
			var st = beatStep % 16, lv = beatLvl, v = beatVol;
			if(beatOn > 0) {
				if(st == 0) { beatPlay.(\kick, 0, 0.9 * v) };
				if((st == 10) and: { lv > 0.45 }) { beatPlay.(\kick, 0, 0.6 * v) };
				if((st == 14) and: { lv > 0.75 } and: { 0.5.coin }) { beatPlay.(\kick, 0, 0.5 * v) };
				if(st == 8) { beatPlay.(\snare, 1, 0.8 * v) };
				if((lv > 0.15) and: { st.even }) {
					beatPlay.(\hat, 2, (if((st % 4) == 2) { 0.35 } { 0.2 }) * v, rrand(0.95, 1.05), rrand(-0.3, 0.3)) };
				if((lv > 0.7) and: { st.odd }) { beatPlay.(\hat, 2, 0.15 * v, 1.2, rrand(-0.5, 0.5)) };
				beatStep = beatStep + 1;
			} { beatStep = 0 };
			(60 / beatBpm.max(60) / 4).wait;               // double croche
		};
	}).play(SystemClock);

	// /voice chemin.wav  (annonce du score)
	OSCdef(\jkVoice, { |m|
		Buffer.readChannel(s, m[1].asString, channels: [0], action: { |b|
			Synth(\jk_sample, [\out, 0, \revBus, revBus, \buf, b, \amp, 0.9, \rev, 0.05], srcGroup);
			SystemClock.sched(b.duration + 0.5, { b.free; nil });
		});
	}, '/voice');

	py.sendMsg('/jokari/ready');
	"Jokari : moteur son prêt".postln;
};
)
