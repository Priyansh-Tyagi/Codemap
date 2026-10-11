import { useEffect, useState } from "react";
import { getFileImpact } from "../services/api";

export default function ImpactPanel({ projectId, filePath, onSelectFile }) {
  const [impact, setImpact] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!projectId || !filePath) {
      setImpact(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    getFileImpact(projectId, filePath)
      .then((data) => {
        if (!cancelled) setImpact(data);
      })
      .catch(() => {
        if (!cancelled) setImpact(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, filePath]);

  if (!filePath) return null;

  return (
    <div className="px-4 py-4 border-t border-line">
      <h3 className="text-[12px] font-semibold text-fg">Change impact</h3>

      {loading && <p className="mt-2 text-[12px] text-faint">Checking...</p>}

      {!loading && impact && (
        <>
          <p className="mt-2 text-[13px] text-muted leading-relaxed">
            Changing this file could affect{" "}
            <span className="font-semibold text-fg tabular-nums">{impact.estimatedAffected}</span>{" "}
            other {impact.estimatedAffected === 1 ? "file" : "files"}.
          </p>

          <ImpactGroup
            label="Directly imports it"
            files={impact.directDependents}
            onSelectFile={onSelectFile}
          />
          <ImpactGroup
            label="Affected indirectly"
            files={impact.indirectDependents}
            onSelectFile={onSelectFile}
          />
        </>
      )}
    </div>
  );
}

function ImpactGroup({ label, files, onSelectFile }) {
  if (files.length === 0) return null;
  return (
    <div className="mt-3">
      <p className="text-[11px] font-medium text-muted">{label}</p>
      <ul className="mt-1 space-y-0.5">
        {files.map((fileId) => (
          <li key={fileId}>
            <button
              onClick={() => onSelectFile(fileId)}
              className="w-full text-left truncate font-mono text-[12px] text-fg-soft hover:text-fg px-1.5 py-1 rounded-md hover:bg-surface-2"
            >
              {fileId}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
