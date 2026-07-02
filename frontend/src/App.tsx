import React, { useState, useEffect, useRef } from 'react';

interface WorkExperience {
  company: string;
  position: string;
  start_date: string;
  end_date?: string;
  skills_used: string[];
  seniority_level: string;
  description?: string;
}

interface Candidate {
  id: string;
  name: string;
  email?: string;
  phone?: string;
  skills: string[];
  industry?: string;
  experience: WorkExperience[];
  extracted_text?: string;
}

interface MatchResult {
  candidate_id: string;
  candidate_name: string;
  score: number;
  breakdown: {
    skills: number;
    experience: number;
    education: number;
    culture_fit: number;
  };
  hard_match: {
    exp_passed: boolean;
    skills_passed: boolean;
    education_passed: boolean;
    relevant_years: number;
    required_years: number;
    matched_required_skills: string[];
    missing_required_skills: string[];
    overall_hard_match_passed: boolean;
    has_english: boolean;
    practical_years: number;
    has_practical_exp: boolean;
    has_worked: boolean;
  };
  strengths: string[];
  missing_skills: string[];
  reasoning: string;
}

interface Weights {
  skills: number;
  experience: number;
  education: number;
  culture_fit: number;
}

const PRESETS = [
  { name: 'Balanced ', weights: { skills: 40, experience: 30, education: 15, culture_fit: 15 } },
  { name: 'Tech Heavy ', weights: { skills: 60, experience: 20, education: 10, culture_fit: 10 } },
  { name: 'Tenure & Lead ', weights: { skills: 30, experience: 50, education: 10, culture_fit: 10 } },
  { name: 'Junior & Academic ', weights: { skills: 35, experience: 15, education: 30, culture_fit: 20 } }
];

export default function App() {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [jdText, setJdText] = useState('');
  const [jdFile, setJdFile] = useState<File | null>(null);
  const [weights, setWeights] = useState<Weights>({
    skills: 40,
    experience: 30,
    education: 15,
    culture_fit: 15
  });
  const [isMatching, setIsMatching] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isLoadingSamples, setIsLoadingSamples] = useState(false);
  const [isLoadingSampleJD, setIsLoadingSampleJD] = useState(false);
  const [results, setResults] = useState<MatchResult[]>([]);
  const [activeTab, setActiveTab] = useState<'match' | 'candidates'>('match');
  const [dragActive, setDragActive] = useState(false);
  const [expandedResult, setExpandedResult] = useState<string | null>(null);
  const [rawTextModal, setRawTextModal] = useState<{ name: string; text: string } | null>(null);
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const jdFileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchCandidates();
  }, []);

  const fetchCandidates = async () => {
    try {
      const res = await fetch('/api/candidates');
      if (res.ok) {
        const data = await res.json();
        setCandidates(data);
      }
    } catch (e) {
      console.error('Error fetching candidates:', e);
    }
  };

  const handleWeightChange = (category: keyof Weights, value: number) => {
    setWeights(prev => {
      const diff = value - prev[category];
      const otherCategories = (Object.keys(prev) as (keyof Weights)[]).filter(k => k !== category);
      
      const otherSum = otherCategories.reduce((sum, k) => sum + prev[k], 0);
      const newWeights = { ...prev };
      newWeights[category] = value;
      
      if (otherSum > 0) {
        otherCategories.forEach(k => {
          const proportion = prev[k] / otherSum;
          newWeights[k] = Math.max(0, Math.round(prev[k] - diff * proportion));
        });
      } else {
        const share = Math.round(diff / otherCategories.length);
        otherCategories.forEach(k => {
          newWeights[k] = Math.max(0, prev[k] - share);
        });
      }
      
      // Correct minor rounding errors to sum exactly to 100
      let currentSum = Object.values(newWeights).reduce((a, b) => a + b, 0);
      let safety = 0;
      while (currentSum !== 100 && safety < 10) {
        const delta = 100 - currentSum;
        const largestCategory = otherCategories.reduce((a, b) => newWeights[a] > newWeights[b] ? a : b);
        newWeights[largestCategory] = Math.max(0, newWeights[largestCategory] + delta);
        currentSum = Object.values(newWeights).reduce((a, b) => a + b, 0);
        safety++;
      }
      
      return newWeights;
    });
  };

  // Drag and drop handlers
  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      uploadCVFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      uploadCVFile(e.target.files[0]);
    }
  };

  const uploadCVFile = async (file: File) => {
    setIsUploading(true);
    const formData = new FormData();
    formData.append("file", file);
    
    try {
      const res = await fetch("/api/upload_cv", {
        method: "POST",
        body: formData
      });
      if (res.ok) {
        await fetchCandidates();
        alert("CV Ingested and Indexed successfully!");
      } else {
        const err = await res.json();
        alert(`Failed to upload: ${err.detail || 'Unknown error'}`);
      }
    } catch (e) {
      console.error(e);
      alert("Network error while uploading CV.");
    } finally {
      setIsUploading(false);
    }
  };

  const handleLoadSamples = async () => {
    setIsLoadingSamples(true);
    try {
      const res = await fetch("/api/load_samples", { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        await fetchCandidates();
        alert(`Successfully ingested ${data.ingested_count} sample CVs from the workspace!`);
      } else {
        alert("Failed to load workspace sample CVs.");
      }
    } catch (e) {
      console.error(e);
      alert("Error loading sample CVs.");
    } finally {
      setIsLoadingSamples(false);
    }
  };

  const handleLoadSampleJD = async () => {
    setIsLoadingSampleJD(true);
    try {
      const res = await fetch("/api/load_sample_jd");
      if (res.ok) {
        const data = await res.json();
        if (data.text) {
          setJdText(data.text);
          if (jdFile) setJdFile(null);
          alert("Sample JD (AI Engineer) text loaded into editor!");
        } else {
          alert(data.error || "Sample JD not found.");
        }
      } else {
        alert("Failed to fetch sample JD.");
      }
    } catch (e) {
      console.error(e);
      alert("Error loading sample JD.");
    } finally {
      setIsLoadingSampleJD(false);
    }
  };

  const handleDeleteCandidate = async (id: string) => {
    if (!confirm("Are you sure you want to delete this candidate?")) return;
    try {
      const res = await fetch(`/api/candidates/${id}`, {
        method: "DELETE"
      });
      if (res.ok) {
        setCandidates(prev => prev.filter(c => c.id !== id));
        setResults(prev => prev.filter(r => r.candidate_id !== id));
      } else {
        const err = await res.json();
        alert(`Failed to delete candidate: ${err.detail || 'Unknown error'}`);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleJDFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setJdFile(e.target.files[0]);
      setJdText(`[FILE ATTACHED: ${e.target.files[0].name}]`);
    }
  };

  const handleMatch = async () => {
    if (!jdText.trim() && !jdFile) {
      alert("Please enter Job Description details or upload a JD document.");
      return;
    }
    if (candidates.length === 0) {
      alert("No candidates uploaded yet. Please ingest at least one CV first.");
      return;
    }

    setIsMatching(true);
    const formData = new FormData();
    if (jdFile) {
      formData.append("jd_file", jdFile);
    } else {
      formData.append("jd_text", jdText);
    }

    // Convert weights to fractions (sum = 1.0)
    const normalizedWeights = {
      skills: weights.skills / 100,
      experience: weights.experience / 100,
      education: weights.education / 100,
      culture_fit: weights.culture_fit / 100
    };
    
    formData.append("weights", JSON.stringify(normalizedWeights));

    try {
      const res = await fetch("/api/match", {
        method: "POST",
        body: formData
      });
      if (res.ok) {
        const data = await res.json();
        setResults(data);
        setExpandedResult(data.length > 0 ? data[0].candidate_id : null);
      } else {
        const err = await res.json();
        alert(`Failed to match: ${err.detail || 'Unknown error'}`);
      }
    } catch (e) {
      console.error(e);
      alert("Error evaluating matches.");
    } finally {
      setIsMatching(false);
    }
  };

  const getCandidateText = (candId: string) => {
    const c = candidates.find(item => item.id === candId);
    return c?.extracted_text || "No parsed text available.";
  };

  return (
    <div className="app-container">
      <header className="neo-header">
        <div className="logo-box">RESUME MATCHER</div>
        <div className="nav-links">
          <a href="#" onClick={(e) => { e.preventDefault(); setActiveTab('match'); }} style={{textDecoration: activeTab === 'match' ? 'underline' : 'none'}}>Matching Hub</a>
          <a href="#" onClick={(e) => { e.preventDefault(); setActiveTab('candidates'); }} style={{textDecoration: activeTab === 'candidates' ? 'underline' : 'none'}}>Candidate Pool ({candidates.length})</a>
        </div>
        <button className="neo-btn small blue" style={{ color: '#fff', cursor: 'default' }}>Pipeline Engaged</button>
      </header>

      {/* Hero Welcome section */}
      <section className="hero-section">
        <div className="hero-text">
          <h1>Finding matching talent is <span className="hl-black">Hard.</span> We make it <span className="hl-blue">easier.</span></h1>
          <p>
            An advanced RAG matching system built on local parsing, semantic vector indexing, deterministic experience scoring, and LLM-guided qualitative analysis. Out-of-the-box support for Vietnamese documents.
          </p>
          <div style={{ display: 'flex', gap: '15px', flexWrap: 'wrap' }}>
            <button className="neo-btn yellow" onClick={() => fileInputRef.current?.click()}>Ingest CV Document</button>
            <button className="neo-btn" onClick={() => jdFileInputRef.current?.click()}>Attach JD PDF</button>
            <button className="neo-btn blue" style={{ color: '#fff' }} onClick={handleLoadSamples} disabled={isLoadingSamples}>
              {isLoadingSamples ? "Parsing Samples..." : "Auto-Load Workspace CVs 📁"}
            </button>
          </div>
          <input type="file" ref={fileInputRef} onChange={handleFileInput} style={{ display: 'none' }} accept=".pdf,.docx,.txt" />
          <input type="file" ref={jdFileInputRef} onChange={handleJDFileUpload} style={{ display: 'none' }} accept=".pdf,.docx,.txt" />
        </div>
        <div className="hero-image">
          <div className="collage-graphic">
            <div className="collage-eye">
              <div className="collage-pupil"></div>
            </div>
            <div style={{ position: 'absolute', bottom: '10px', right: '10px', fontSize: '2.5rem' }}></div>
            <div style={{ position: 'absolute', top: '10px', left: '10px', fontSize: '2rem' }}></div>
          </div>
        </div>
      </section>

      {/* Main Workspace */}
      {activeTab === 'match' ? (
        <div className="grid-workspace">
          {/* Left Panel: Inputs and Configurations */}
          <div className="workspace-inputs">
            <div className="neo-card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
                <h3 style={{ fontFamily: 'Space Grotesk', margin: 0 }}>1. Drag & Ingest CVs</h3>
                <button 
                  className="neo-btn small yellow" 
                  style={{ fontSize: '0.75rem', padding: '4px 8px' }}
                  onClick={handleLoadSamples}
                  disabled={isLoadingSamples}
                >
                  {isLoadingSamples ? "Loading..." : "Load Workspace CVs 📁"}
                </button>
              </div>

              <div 
                className={`drag-zone ${dragActive ? 'dragging' : ''}`}
                onDragEnter={handleDrag}
                onDragOver={handleDrag}
                onDragLeave={handleDrag}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
              >
                <p style={{ fontWeight: 600 }}>{isUploading ? "Extracting & Indexing..." : "Drag & Drop Resume PDF/DOCX here"}</p>
                <p style={{ fontSize: '0.85rem', color: '#666', marginTop: '5px' }}>or click to browse local files</p>
              </div>

              {candidates.length > 0 && (
                <div>
                  <h4 style={{ fontSize: '0.9rem', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Currently Ingested:</h4>
                  <div style={{ maxHeight: '180px', overflowY: 'auto', border: '2px solid #1a1a1a', padding: '8px', backgroundColor: '#fff' }}>
                    {candidates.map(cand => (
                      <div key={cand.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 4px', borderBottom: '1px solid #eee' }}>
                        <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>{cand.name}</span>
                        <div style={{ display: 'flex', gap: '5px' }}>
                          <button 
                            className="neo-btn small blue" 
                            style={{ padding: '2px 6px', fontSize: '0.75rem', color: '#fff' }} 
                            onClick={(e) => {
                              e.stopPropagation();
                              setRawTextModal({ name: cand.name, text: cand.extracted_text || "No parsed text available." });
                            }}
                          >
                            Text
                          </button>
                          <button className="neo-btn red small" style={{ padding: '2px 6px', fontSize: '0.75rem' }} onClick={(e) => { e.stopPropagation(); handleDeleteCandidate(cand.id); }}>Remove</button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="neo-card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
                <h3 style={{ fontFamily: 'Space Grotesk', margin: 0 }}>2. Job Description (JD)</h3>
                <button 
                  className="neo-btn small blue" 
                  style={{ fontSize: '0.75rem', padding: '4px 8px', color: '#fff' }}
                  onClick={handleLoadSampleJD}
                  disabled={isLoadingSampleJD}
                >
                  {isLoadingSampleJD ? "Loading..." : "Load Sample JD 📄"}
                </button>
              </div>

              <textarea 
                className="neo-input" 
                rows={6} 
                placeholder="Paste Job Description specifications here..."
                value={jdText}
                onChange={(e) => { setJdText(e.target.value); if (jdFile) setJdFile(null); }}
              ></textarea>
              {jdFile && (
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '-10px', marginBottom: '20px', padding: '8px', border: '2px solid #1a1a1a', backgroundColor: '#eef2ff' }}>
                  <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>📎 Attached: {jdFile.name}</span>
                  <button className="neo-btn small red" style={{ padding: '2px 6px' }} onClick={() => { setJdFile(null); setJdText(''); }}>Clear</button>
                </div>
              )}
            </div>

            <div className="neo-card">
              <h3 style={{ marginBottom: '10px', fontFamily: 'Space Grotesk' }}>3. Rubric Weights (Sum: 100%)</h3>
              
              <div style={{ marginBottom: '15px' }}>
                <span style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', color: '#666' }}>Presets:</span>
                <div className="preset-container">
                  {PRESETS.map(p => {
                    const isActive = weights.skills === p.weights.skills && 
                                     weights.experience === p.weights.experience && 
                                     weights.education === p.weights.education && 
                                     weights.culture_fit === p.weights.culture_fit;
                    return (
                      <button 
                        key={p.name} 
                        className={`preset-badge-btn ${isActive ? 'active' : ''}`}
                        onClick={() => setWeights(p.weights)}
                      >
                        {p.name}
                      </button>
                    );
                  })}
                </div>
              </div>
              
              <div className="weight-control">
                <div className="weight-header">
                  <span>Technical Skills</span>
                  <span>{weights.skills}%</span>
                </div>
                <div className="slider-container">
                  <input type="range" className="neo-slider" min={20} max={60} value={weights.skills} onChange={(e) => handleWeightChange('skills', parseInt(e.target.value))} />
                </div>
              </div>

              <div className="weight-control">
                <div className="weight-header">
                  <span>Experience & Domain</span>
                  <span>{weights.experience}%</span>
                </div>
                <div className="slider-container">
                  <input type="range" className="neo-slider" min={10} max={50} value={weights.experience} onChange={(e) => handleWeightChange('experience', parseInt(e.target.value))} />
                </div>
              </div>

              <div className="weight-control">
                <div className="weight-header">
                  <span>Education Credentials</span>
                  <span>{weights.education}%</span>
                </div>
                <div className="slider-container">
                  <input type="range" className="neo-slider" min={0} max={30} value={weights.education} onChange={(e) => handleWeightChange('education', parseInt(e.target.value))} />
                </div>
              </div>

              <div className="weight-control">
                <div className="weight-header">
                  <span>Soft Skills / Culture Fit</span>
                  <span>{weights.culture_fit}%</span>
                </div>
                <div className="slider-container">
                  <input type="range" className="neo-slider" min={0} max={30} value={weights.culture_fit} onChange={(e) => handleWeightChange('culture_fit', parseInt(e.target.value))} />
                </div>
              </div>

              <button className="neo-btn blue" style={{ width: '100%', marginTop: '15px', color: '#fff' }} onClick={handleMatch} disabled={isMatching}>
                {isMatching ? "Calculating Matches..." : "Evaluate Candidates"}
              </button>
            </div>
          </div>

          {/* Right Panel: Ranked Match Dashboard */}
          <div className="workspace-results">
            <div className="neo-card" style={{ minHeight: '500px' }}>
              <h2 style={{ fontFamily: 'Space Grotesk', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '10px' }}>
                Evaluation Dashboard
                {results.length > 0 && <span className="hl-orange" style={{ fontSize: '0.9rem', padding: '3px 8px' }}>Ranked</span>}
              </h2>
              
              {results.length === 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '350px', color: '#888' }}>
                  <span style={{ fontSize: '3.5rem', marginBottom: '15px' }}>📊</span>
                  <p style={{ fontWeight: 600 }}>No evaluations generated yet.</p>
                  <p style={{ fontSize: '0.85rem', textAlign: 'center', marginTop: '5px', maxWidth: '300px' }}>
                    Select weights, paste the target JD, and click "Evaluate Candidates" to run the 6-layer RAG matching process.
                  </p>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  {results.map((match, index) => {
                    const isExpanded = expandedResult === match.candidate_id;
                    const hard = match.hard_match;
                    const scoreClass = match.score >= 80 ? 'high' : match.score >= 50 ? 'medium' : 'low';
                    
                    return (
                      <div key={match.candidate_id} className="neo-card interactive" style={{ padding: '20px', margin: 0 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }} onClick={() => setExpandedResult(isExpanded ? null : match.candidate_id)}>
                          <div>
                            <span style={{ fontWeight: 800, fontSize: '1.25rem', fontFamily: 'Space Grotesk' }}>
                              #{index + 1} {match.candidate_name}
                            </span>
                            <div style={{ display: 'flex', gap: '10px', marginTop: '4px', flexWrap: 'wrap' }}>
                              <span className={`status-badge ${hard.overall_hard_match_passed ? 'passed' : 'failed'}`}>
                                Hard-Match: {hard.overall_hard_match_passed ? "PASSED" : "FAILED"}
                              </span>
                              {hard.has_english && <span className="status-badge passed">English Cert Active</span>}
                              {!hard.has_worked && <span className="status-badge failed">Rejected: Projects Only</span>}
                            </div>
                          </div>
                          <div className={`score-badge ${scoreClass}`}>
                            {match.score}%
                          </div>
                        </div>

                        {isExpanded && (
                          <div style={{ marginTop: '20px', borderTop: '2px solid #1a1a1a', paddingTop: '20px' }}>
                            <div style={{ display: 'grid', gridTemplateColumns: '1.1fr 0.9fr', gap: '20px' }}>
                              {/* Left Column: Breakdown Progress */}
                              <div>
                                <h4 style={{ fontFamily: 'Space Grotesk', marginBottom: '10px' }}>Weighted Alignment Breakdown:</h4>
                                
                                <div style={{ marginBottom: '10px' }}>
                                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', fontWeight: 700 }}>
                                    <span>Skills Score (Weight {weights.skills}%)</span>
                                    <span>{match.breakdown.skills}/100</span>
                                  </div>
                                  <div className="progress-bar-container">
                                    <div className="progress-bar-fill skills" style={{ width: `${match.breakdown.skills}%` }}></div>
                                  </div>
                                </div>

                                <div style={{ marginBottom: '10px' }}>
                                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', fontWeight: 700 }}>
                                    <span>Experience Score (Weight {weights.experience}%)</span>
                                    <span>{match.breakdown.experience}/100</span>
                                  </div>
                                  <div className="progress-bar-container">
                                    <div className="progress-bar-fill experience" style={{ width: `${match.breakdown.experience}%` }}></div>
                                  </div>
                                </div>

                                <div style={{ marginBottom: '10px' }}>
                                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', fontWeight: 700 }}>
                                    <span>Education Score (Weight {weights.education}%)</span>
                                    <span>{match.breakdown.education}/100</span>
                                  </div>
                                  <div className="progress-bar-container">
                                    <div className="progress-bar-fill education" style={{ width: `${match.breakdown.education}%` }}></div>
                                  </div>
                                </div>

                                <div style={{ marginBottom: '10px' }}>
                                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', fontWeight: 700 }}>
                                    <span>Soft Skills / Culture Fit (Weight {weights.culture_fit}%)</span>
                                    <span>{match.breakdown.culture_fit}/100</span>
                                  </div>
                                  <div className="progress-bar-container">
                                    <div className="progress-bar-fill culture" style={{ width: `${match.breakdown.culture_fit}%` }}></div>
                                  </div>
                                </div>
                              </div>

                              {/* Right Column: Hard-match checklist */}
                              <div>
                                <h4 style={{ fontFamily: 'Space Grotesk', marginBottom: '10px' }}>Hard-Filter Constraints:</h4>
                                <div className="check-item">
                                  <span className={`check-indicator ${hard.exp_passed ? 'pass' : 'fail'}`}>{hard.exp_passed ? "✓" : "✗"}</span>
                                  <span>Relevant Tenure ({hard.relevant_years} yrs / {hard.required_years} yrs req)</span>
                                </div>
                                <div className="check-item">
                                  <span className={`check-indicator ${hard.skills_passed ? 'pass' : 'fail'}`}>{hard.skills_passed ? "✓" : "✗"}</span>
                                  <span>Technical Core Skills Match (50%+)</span>
                                </div>
                                <div className="check-item">
                                  <span className={`check-indicator ${hard.education_passed ? 'pass' : 'fail'}`}>{hard.education_passed ? "✓" : "✗"}</span>
                                  <span>Academic Level Requirement</span>
                                </div>
                                <div className="check-item">
                                  <span className={`check-indicator ${hard.has_english ? 'pass' : 'fail'}`}>{hard.has_english ? "✓" : "✗"}</span>
                                  <span>English Certificate (TOEIC/IELTS)</span>
                                </div>
                                <div className="check-item">
                                  <span className={`check-indicator ${hard.has_worked ? 'pass' : 'fail'}`}>{hard.has_worked ? "✓" : "✗"}</span>
                                  <span>Corporate Job Experience (No Projects-Only)</span>
                                </div>
                              </div>
                            </div>

                            {/* Strengths and missing skills */}
                            <div style={{ marginTop: '15px' }}>
                              <h4 style={{ fontFamily: 'Space Grotesk', marginBottom: '5px' }}>Strengths:</h4>
                              <div className="tags-list">
                                {match.strengths.map((st, i) => (
                                  <span key={i} className="neo-tag strength">{st}</span>
                                ))}
                              </div>
                            </div>

                            {match.missing_skills.length > 0 && (
                              <div style={{ marginTop: '10px' }}>
                                <h4 style={{ fontFamily: 'Space Grotesk', marginBottom: '5px' }}>Missing Required / Preferred Skills:</h4>
                                <div className="tags-list">
                                  {match.missing_skills.map((sk, i) => (
                                    <span key={i} className="neo-tag missing">{sk}</span>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Actions row */}
                            <div style={{ marginTop: '20px', display: 'flex', gap: '10px' }}>
                              <button 
                                className="neo-btn small blue" 
                                style={{ color: '#fff' }}
                                onClick={() => setRawTextModal({ 
                                  name: match.candidate_name, 
                                  text: getCandidateText(match.candidate_id) 
                                })}
                              >
                                View Extracted CV Text 📄
                              </button>
                            </div>

                            {/* Accordion qualitative reasoning */}
                            <div className="accordion-header" onClick={() => setExpandedResult(isExpanded ? null : match.candidate_id)}>
                              <span>Qualitative Assessment & Feedback</span>
                              <span>▼</span>
                            </div>
                            <div className="accordion-content">
                              {match.reasoning}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      ) : (
        /* Candidates Pool Tab */
        <div className="neo-card">
          <h2 style={{ fontFamily: 'Space Grotesk', marginBottom: '20px' }}>Ingested Candidates Pool ({candidates.length})</h2>
          {candidates.length === 0 ? (
            <div style={{ padding: '30px', textAlign: 'center' }}>
              <p style={{ color: '#888', fontWeight: 600, marginBottom: '15px' }}>No candidates currently indexed in the vector database.</p>
              <button className="neo-btn yellow" onClick={handleLoadSamples} disabled={isLoadingSamples}>
                {isLoadingSamples ? "Loading samples..." : "Load Workspace Samples 📁"}
              </button>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
              {candidates.map(cand => (
                <div key={cand.id} className="neo-card" style={{ margin: 0, padding: '20px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                      <h3 style={{ fontFamily: 'Space Grotesk', fontWeight: 800 }}>{cand.name}</h3>
                      <div className="meta-details">
                        <div className="meta-item">📧 {cand.email || "No Email"}</div>
                        <div className="meta-item">📞 {cand.phone || "No Phone"}</div>
                        <div className="meta-item">🏢 Industry: {cand.industry || "Unknown"}</div>
                      </div>
                      
                      <div style={{ marginTop: '15px' }}>
                        <span style={{ fontWeight: 700, fontSize: '0.85rem' }}>Parsed Skills: </span>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px', marginTop: '5px' }}>
                          {cand.skills.map((sk, i) => (
                            <span key={i} className="neo-tag" style={{ fontSize: '0.75rem', padding: '2px 6px' }}>{sk}</span>
                          ))}
                        </div>
                      </div>

                      {cand.experience.length > 0 && (
                        <div style={{ marginTop: '15px' }}>
                          <span style={{ fontWeight: 700, fontSize: '0.85rem' }}>Experience Timeline:</span>
                          <ul style={{ paddingLeft: '20px', marginTop: '5px', fontSize: '0.85rem', listStyleType: 'square' }}>
                            {cand.experience.map((exp, idx) => (
                              <li key={idx} style={{ marginBottom: '4px' }}>
                                <strong>{exp.position}</strong> at {exp.company} ({exp.start_date} to {exp.end_date || 'Present'}) - <em>{exp.seniority_level}</em>
                                {exp.skills_used.length > 0 && (
                                  <div style={{ fontSize: '0.75rem', color: '#666', marginTop: '2px' }}>
                                    Skills: {exp.skills_used.join(', ')}
                                  </div>
                                )}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                      <button 
                        className="neo-btn small blue" 
                        style={{ color: '#fff' }}
                        onClick={() => setRawTextModal({ name: cand.name, text: cand.extracted_text || "No parsed text available." })}
                      >
                        View CV Text 📄
                      </button>
                      <button className="neo-btn red small" onClick={() => handleDeleteCandidate(cand.id)}>Delete Candidate</button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Raw Text Modal Dialog */}
      {rawTextModal && (
        <div className="neo-modal-overlay" onClick={() => setRawTextModal(null)}>
          <div className="neo-modal-content" onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', borderBottom: '2px solid #1a1a1a', paddingBottom: '10px' }}>
              <h3 style={{ fontFamily: 'Space Grotesk', fontWeight: 800 }}>Raw Extracted Text: {rawTextModal.name}</h3>
              <button className="neo-btn small red" onClick={() => setRawTextModal(null)}>Close</button>
            </div>
            <pre style={{ 
              whiteSpace: 'pre-wrap', 
              fontFamily: 'Courier New, Courier, monospace', 
              fontSize: '0.9rem', 
              backgroundColor: '#f8f9fa', 
              padding: '15px', 
              border: '1px solid #ddd',
              maxHeight: '60vh',
              overflowY: 'auto'
            }}>
              {rawTextModal.text}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
