use std::net::UdpSocket;
use serde::Deserialize;
#[derive(Debug, Deserialize)]
struct BciMsg { yaw:f32, altitude:f32, speed:f32, ts:f64 }
fn main() -> std::io::Result<()> {
    let sock = UdpSocket::bind("127.0.0.1:5005")?;
    println!("[RUN] UDP 127.0.0.1:5005");
    let mut buf=[0u8;2048];
    loop {
        let (len,_) = sock.recv_from(&mut buf)?;
        if let Ok(txt) = std::str::from_utf8(&buf[..len]) {
            if let Ok(m)=serde_json::from_str::<BciMsg>(txt) {
                println!("Yaw={:+.2} Alt={:+.2} Spd={:.2}", m.yaw,m.altitude,m.speed);
                // TODO: 在这里接入 MAVSDK/ROS2 或模拟器 API
            }
        }
    }
}
