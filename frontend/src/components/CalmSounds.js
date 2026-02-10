import React, { useState, useRef, useEffect } from "react";
import { FiMusic, FiPlay, FiPause, FiSearch } from "react-icons/fi";
import "./CalmSounds.css";

const calmSoundsData = [
  {
    category: "Gym",
    type: "Phonk",
    sounds: [
      { title: "Phonk Energy", url: "/sounds/phonk1.mp3" },
      { title: "Gym Beast Mode", url: "/sounds/phonk2.mp3" }
    ]
  },
  {
    category: "Meditation",
    type: "Calm",
    sounds: [
      { title: "Deep Relax", url: "/sounds/calm1.mp3" },
      { title: "Peace Mind", url: "/sounds/calm2.mp3" }
    ]
  },
  {
    category: "Sleep",
    type: "LoFi",
    sounds: [
      { title: "Night Chill", url: "/sounds/lofi1.mp3" },
      { title: "Dream Waves", url: "/sounds/lofi2.mp3" }
    ]
  },
  {
    category: "Nature",
    type: "Ambient",
    sounds: [
      { title: "Rainforest", url: "/sounds/nature1.mp3" },
      { title: "Ocean Waves", url: "/sounds/nature2.mp3" },
      { title: "Mountain Stream", url: "/sounds/nature3.mp3" }
    ]
  },
  {
    category: "Focus",
    type: "Instrumental",
    sounds: [
      { title: "Piano Focus", url: "/sounds/focus1.mp3" },
      { title: "Concentration Beats", url: "/sounds/focus2.mp3" }
    ]
  },
  {
    category: "Relaxation",
    type: "Jazz",
    sounds: [
      { title: "Smooth Jazz Evening", url: "/sounds/jazz1.mp3" },
      { title: "Coffee Shop Jazz", url: "/sounds/jazz2.mp3" }
    ]
  },
  {
    category: "Weather",
    type: "Rain & Storm",
    sounds: [
      { title: "Rain Drops", url: "/sounds/rain1.mp3" },
      { title: "Thunderstorm", url: "/sounds/rain2.mp3" }
    ]
  },
  {
    category: "Classical",
    type: "Orchestral",
    sounds: [
      { title: "Mozart Relaxation", url: "/sounds/classical1.mp3" },
      { title: "Beethoven Calm", url: "/sounds/classical2.mp3" }
    ]
  }
];

const CalmSounds = () => {
  const [currentSound, setCurrentSound] = useState(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [duration, setDuration] = useState(0);
  const [searchTerm, setSearchTerm] = useState("");

  const audioRef = useRef(new Audio());

  // Play or pause a sound
  const playSound = (sound) => {
    const audio = audioRef.current;

    if (currentSound?.url === sound.url && isPlaying) {
      audio.pause();
      setIsPlaying(false);
      return;
    }

    audio.src = sound.url;
    audio.play();
    setCurrentSound(sound);
    setIsPlaying(true);
    setProgress(0);
  };

  // Update progress and duration
  useEffect(() => {
    const audio = audioRef.current;
    const updateProgress = () => setProgress(audio.currentTime);
    const setMeta = () => setDuration(audio.duration || 0);

    audio.addEventListener("timeupdate", updateProgress);
    audio.addEventListener("loadedmetadata", setMeta);

    // Cleanup function runs on component unmount
    return () => {
      audio.pause(); // stop audio when leaving tab
      setIsPlaying(false);
      setCurrentSound(null);
      audio.removeEventListener("timeupdate", updateProgress);
      audio.removeEventListener("loadedmetadata", setMeta);
    };
  }, []);

  // Seek functionality
  const handleSeek = (e) => {
    const audio = audioRef.current;
    const value = Number(e.target.value);
    audio.currentTime = value;
    setProgress(value);
  };

  // Format time mm:ss
  const formatTime = (time) => {
    if (!time || isNaN(time)) return "0:00";
    const min = Math.floor(time / 60);
    const sec = Math.floor(time % 60);
    return `${min}:${sec < 10 ? "0" : ""}${sec}`;
  };

  // Highlight matched text in song titles
  const highlightMatch = (text, query) => {
    if (!query) return text;
    const regex = new RegExp(`(${query})`, "gi");
    const parts = text.split(regex);
    return parts.map((part, i) =>
      regex.test(part) ? (
        <span key={i} className="highlight">{part}</span>
      ) : (
        part
      )
    );
  };

  // Filter songs based on search term
  const filteredData = calmSoundsData
    .map((cat) => ({
      ...cat,
      sounds: cat.sounds.filter((sound) =>
        sound.title.toLowerCase().includes(searchTerm.toLowerCase())
      )
    }))
    .filter((cat) => cat.sounds.length > 0);

  return (
    <div className="calm-container">
      <h2 className="calm-title">
        <FiMusic /> Calm Sounds & Music Therapy
      </h2>

      {/* SEARCH BAR */}
      <div className="search-box">
        <FiSearch style={{ position: "absolute", top: "50%", left: "12px", transform: "translateY(-50%)", color: "rgba(255,255,255,0.6)" }} />
        <input
          type="text"
          placeholder="🔍Search for a sound...!!"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          style={{ paddingLeft: "40px" }}
        />
      </div>

      {/* SONG CARDS */}
      {filteredData.length > 0 ? (
        filteredData.map((cat, index) => (
          <div key={index} className="category-card">
            <h3 className="category-title">
              {cat.category} • {cat.type}
            </h3>

            <div className="sounds-grid">
              {cat.sounds.map((sound, i) => (
                <div
                  key={i}
                  className={`sound-box ${currentSound?.url === sound.url ? "active-sound" : ""}`}
                  onClick={() => playSound(sound)}
                >
                  <h4>{highlightMatch(sound.title, searchTerm)}</h4>
                  <button className="play-btn">
                    {currentSound?.url === sound.url && isPlaying ? <FiPause /> : <FiPlay />}
                  </button>
                </div>
              ))}
            </div>
          </div>
        ))
      ) : (
        <p className="not-found" style={{ color: "white", textAlign: "center", marginTop: "20px" }}>
          🔍 Sound not found
        </p>
      )}

      {/* MUSIC PLAYER */}
      {currentSound && isPlaying && (
        <div className="music-player">
          <div className="player-content">
            <span className="now-playing">🎧 {currentSound.title}</span>

            <input
              type="range"
              min="0"
              max={duration || 0}
              value={progress}
              onChange={handleSeek}
              className="seek-bar"
            />

            <div className="time-info">
              <span>{formatTime(progress)}</span>
              <span>{formatTime(duration)}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default CalmSounds;
