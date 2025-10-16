use std::net::UdpSocket;
use serde::Deserialize;
#[derive(Debug, Deserialize)]
struct BciMsg {
    yaw: f32,
    altitude: f32,
    pitch: Option<f32>,
    throttle: Option<f32>,
    speed: Option<f32>,
    ts: f64,
}
fn main() -> std::io::Result<()> {
    let sock = UdpSocket::bind("127.0.0.1:5005")?;
    println!("[RUN] UDP 127.0.0.1:5005");
    let mut buf=[0u8;2048];
    loop {
        let (len,_) = sock.recv_from(&mut buf)?;
        if let Ok(txt) = std::str::from_utf8(&buf[..len]) {
            if let Ok(m)=serde_json::from_str::<BciMsg>(txt) {
                let pitch = m.pitch.unwrap_or(0.0);
                let throttle = m.throttle.unwrap_or_else(|| m.speed.unwrap_or(0.0) * 2.0 - 1.0);
                println!("Yaw={:+.2} Alt={:+.2} Pitch={:+.2} Thr={:+.2}", m.yaw,m.altitude,pitch,throttle);
                // TODO: 在这里接入 MAVSDK/ROS2 或模拟器 API
            }
        }
    }
}
