import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../../lib/api";
import { useSession } from "../../context/SessionContext";

export default function Verify() {
  const [params] = useSearchParams();
  const [error, setError] = useState("");
  const { setMember } = useSession();
  const navigate = useNavigate();

  useEffect(() => {
    const token = params.get("token");
    if (!token) {
      setError("Missing link token.");
      return;
    }
    api
      .post<{ token: string; first_name: string }>("/api/auth/member/verify", { token })
      .then((res) => {
        setMember({ token: res.token, firstName: res.first_name });
        navigate("/screening", { replace: true });
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Link is invalid or expired"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  return (
    <div className="app-shell" style={{ paddingTop: 64 }}>
      <div className="card" style={{ textAlign: "center" }}>
        {error ? (
          <p className="error-text" style={{ marginBottom: 0 }}>
            {error}
          </p>
        ) : (
          <>
            <span className="spinner" style={{ marginBottom: 12 }} />
            <p className="muted" style={{ marginBottom: 0 }}>
              Verifying your link…
            </p>
          </>
        )}
      </div>
    </div>
  );
}
