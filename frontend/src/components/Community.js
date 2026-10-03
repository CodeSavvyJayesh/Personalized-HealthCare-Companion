import React, { useState, useEffect } from "react";
import API_URL from "../config";
import { apiFetch } from "../api";
import {
  FiUsers,
  FiMessageSquare,
  FiHeart,
  FiShare2,
  FiClock,
} from "react-icons/fi";
import "./Community.css";

function Community({ userId }) {
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newPostContent, setNewPostContent] = useState("");
  const [toast, setToast] = useState(null);
  // Shown in place of a post the safety layer declined to publish. It stays
  // until dismissed: a list of helplines must not vanish like a toast.
  const [safetyNotice, setSafetyNotice] = useState(null);

  useEffect(() => {
    const fetchPosts = async () => {
      try {
        const res = await apiFetch(`${API_URL}/community/posts`);
        const data = res;

        if (data.success) {
          setPosts(data.posts);
        }
      } catch (err) {
        console.error("Failed to fetch community posts", err);
      } finally {
        setLoading(false);
      }
    };

    fetchPosts();
  }, []);

  const showToast = (message, type = "success") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  const handleCreatePost = async () => {
    if (!newPostContent.trim()) {
      showToast("Post content cannot be empty", "error");
      return;
    }

    if (!userId) {
      showToast("Please log in to post", "error");
      return;
    }

    try {
      const res = await apiFetch(`${API_URL}/community/posts`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ content: newPostContent }),
      });

      const data = res;

      if (data.safety_notice) {
        setSafetyNotice(data.safety_notice);
        return;
      }

      if (data.success) {
        setSafetyNotice(null);
        showToast("Post created successfully!");
        setNewPostContent("");

        // Refetch posts
        const updatedRes = await apiFetch(`${API_URL}/community/posts`);
        const updatedData = updatedRes;

        if (updatedData.success) {
          setPosts(updatedData.posts);
        }
      } else {
        showToast("Failed to create post", "error");
      }
    } catch (err) {
      console.error("Error creating post", err);
      showToast(err.message || "Couldn't publish your post", "error");
    }
  };

  const handleLike = async (postId) => {
    if (!userId) {
      showToast("Please log in to like posts", "error");
      return;
    }

    try {
      const res = await apiFetch(
        `${API_URL}/community/posts/${postId}/like`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({}),
        }
      );

      const data = res;

      if (data.success) {
        // Update local state for immediate feedback
        setPosts(
          posts.map((post) => {
            if (post._id === postId) {
              const isLiked = post.liked_by_me;

              return {
                ...post,
                liked_by_me: !isLiked,
                like_count: (post.like_count || 0) + (isLiked ? -1 : 1),
              };
            }

            return post;
          })
        );
      }
    } catch (err) {
      console.error("Error liking post", err);
    }
  };

  const timeAgo = (dateString) => {
    const date = new Date(dateString);
    const now = new Date();

    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHrs = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHrs / 24);

    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHrs < 24) return `${diffHrs}h ago`;

    return `${diffDays}d ago`;
  };

  return (
    <div className="community-container">
      {toast && (
        <div className={`toast-notification ${toast.type}`}>
          <span>{toast.message}</span>
        </div>
      )}

      <div className="community-header">
        <h1>
          <FiUsers /> Community Support
        </h1>

        <p>
          Share your thoughts, read others' experiences, and support each
          other.
        </p>
      </div>

      <div className="community-content">
        {safetyNotice && (
          <div
            role="alert"
            style={{
              marginBottom: "1.25rem",
              padding: "1.25rem 1.4rem",
              borderRadius: "16px",
              border: "1.5px solid rgba(251, 191, 36, 0.55)",
              background:
                "linear-gradient(135deg, rgba(251,191,36,0.14), rgba(251,113,133,0.10))",
              color: "var(--text-primary)",
              lineHeight: 1.65,
              whiteSpace: "pre-wrap",
            }}
          >
            <strong style={{ display: "block", marginBottom: "0.5rem" }}>
              Your post wasn't published — but please read this.
            </strong>
            {safetyNotice.replace(/\*\*/g, "")}
            <div style={{ marginTop: "0.9rem" }}>
              <button
                type="button"
                className="action-btn"
                onClick={() => setSafetyNotice(null)}
              >
                Close
              </button>
            </div>
          </div>
        )}

        <div className="create-post-card">
          <textarea
            placeholder="Share what's on your mind..."
            value={newPostContent}
            onChange={(e) => setNewPostContent(e.target.value)}
            rows={4}
          />

          <div className="create-post-actions">
            <button className="post-btn" onClick={handleCreatePost}>
              <FiMessageSquare /> Post
            </button>
          </div>
        </div>

        <div className="posts-feed">
          {loading ? (
            <div className="loading-state">
              Loading community posts...
            </div>
          ) : posts.length > 0 ? (
            posts.map((post) => (
              <div key={post._id} className="post-card">
                <div className="post-header">
                  <div className="post-author">
                    <div className="author-avatar">
                      {(post.author || "M").charAt(0).toUpperCase()}
                    </div>

                    <span className="author-name">
                      {post.author || "Member"}
                    </span>
                  </div>

                  <div className="post-time">
                    <FiClock /> {timeAgo(post.created_at)}
                  </div>
                </div>

                <div className="post-body">
                  {post.content}
                </div>

                <div className="post-footer">
                  <button
                    className={`action-btn ${
                      post.liked_by_me ? "liked" : ""
                    }`}
                    onClick={() => handleLike(post._id)}
                  >
                    <FiHeart
                      className={
                        post.liked_by_me ? "filled" : ""
                      }
                    />

                    {post.like_count || 0}
                  </button>

                  <button className="action-btn">
                    <FiShare2 /> Share
                  </button>
                </div>
              </div>
            ))
          ) : (
            <div className="empty-state">
              <p>
                No posts yet. Be the first to share something!
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default Community;