use std::path::{Path, PathBuf};
use std::process::Command;

use serde_json::Value;

const HOMEBREW_BIN_DIRS: [&str; 2] = ["/opt/homebrew/bin", "/usr/local/bin"];

fn tool_path(name: &str) -> PathBuf {
    for dir in HOMEBREW_BIN_DIRS {
        let candidate = Path::new(dir).join(name);
        if candidate.exists() {
            return candidate;
        }
    }
    if let Ok(home) = std::env::var("HOME") {
        let candidate = Path::new(&home).join(".local/bin").join(name);
        if candidate.exists() {
            return candidate;
        }
    }
    PathBuf::from(name)
}

fn repo_root() -> PathBuf {
    if let Ok(root) = std::env::var("HALFBOLD_REPO") {
        return PathBuf::from(root);
    }
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest_dir
        .join("../..")
        .canonicalize()
        .unwrap_or(manifest_dir)
}

fn api_error(value: &Value, stdout: &str, stderr: &str) -> String {
    match value.get("error").and_then(Value::as_str) {
        Some(message) => message.to_string(),
        None => format!("halfbold-api failed\n{stdout}\n{stderr}"),
    }
}

#[tauri::command]
async fn api(args: Vec<String>) -> Result<Value, String> {
    let output = Command::new(tool_path("uv"))
        .arg("run")
        .arg("--project")
        .arg(repo_root())
        .arg("halfbold-api")
        .args(&args)
        .output()
        .map_err(|err| format!("could not run uv: {err}"))?;
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    let value: Value = serde_json::from_str(stdout.trim())
        .map_err(|_| format!("halfbold-api did not return JSON\n{stdout}\n{stderr}"))?;
    if output.status.success() {
        Ok(value)
    } else {
        Err(api_error(&value, &stdout, &stderr))
    }
}

#[tauri::command]
async fn read_font(path: String) -> Result<tauri::ipc::Response, String> {
    let lowered = path.to_lowercase();
    if !(lowered.ends_with(".ttf") || lowered.ends_with(".otf")) {
        return Err(format!("{path} is not a font file"));
    }
    let bytes = std::fs::read(&path).map_err(|err| format!("{path}: {err}"))?;
    Ok(tauri::ipc::Response::new(bytes))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![api, read_font])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn api_error_prefers_json_message() {
        let value: Value = serde_json::from_str(r#"{"error":"boom"}"#).unwrap();
        assert_eq!(api_error(&value, "", ""), "boom");
    }

    #[test]
    fn api_error_falls_back_to_output() {
        let value = Value::Null;
        let message = api_error(&value, "out", "err");
        assert!(message.contains("out") && message.contains("err"));
    }

    #[test]
    fn repo_root_has_pyproject() {
        assert!(repo_root().join("pyproject.toml").exists());
    }
}
