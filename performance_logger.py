# performance_logger.py
import json
import pandas as pd
import matplotlib.pyplot as plt
import logging
import datetime
import os
import numpy as np
import matplotlib.ticker as ticker
import matplotlib.dates as mdates
import matplotlib

def get_timestamped_filename(base_name):
    # 형식: 20260221_201530_cpu_graph.png
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{now}_{base_name}.png"

# CPU, FPS, RAM을 하나의 차트로 통합하고 상태 변화 지점에 점을 찍어 그래프로 저장
def draw_total_graph(log_path, output_dir):
    
    # 한글 폰트 설정 (Windows 기준)
    matplotlib.rcParams['font.family'] = 'Malgun Gothic'
    matplotlib.rcParams['axes.unicode_minus'] = False

    records = []
    if not os.path.exists(log_path):
        return

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    
    df = pd.DataFrame(records)
    if df.empty:
        logging.error("그래프 생성 실패: 로그 데이터가 비어 있습니다.")
        return
    
    numeric_cols = ['cpu', 'fps', 'meminfo', 'private_dirty', 'gl_mtrack']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = (
                pd.to_numeric(df[col], errors='coerce')
                .ffill()
                .fillna(0)
            )
            
    if 'time' not in df.columns:
        logging.error(f"그래프 생성 실패: 'time' 컬럼이 없습니다. 현재 컬럼: {df.columns.tolist()}")
        return

    df['time'] = pd.to_datetime(df['time'])
    
    active_df = df[df['state'] != 'IDLE_CHECK'].reset_index(drop=True)

    duration_min = (df['time'].max() - df['time'].min()).total_seconds() / 60

    if len(active_df) > 1:
        mem_diff = active_df['meminfo'].iloc[-1] - active_df['meminfo'].iloc[0]
    else:
        mem_diff = 0
    leak_rate_min = mem_diff / duration_min if duration_min > 0 else 0
    DEVICE_TOTAL_MB = 12288
    oom_threshold = DEVICE_TOTAL_MB * 0.9  
    remaining_mem = oom_threshold - df['meminfo'].iloc[-1]
    minutes_to_oom = remaining_mem / leak_rate_min if leak_rate_min > 1.0 else float('inf')

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(15, 12), sharex=True)
    plt.subplots_adjust(hspace=0.2)

    metrics = [
        (ax1, 'cpu', 'CPU Usage (%)', 'tab:red'),
        (ax2, 'fps', 'Frame Rate (FPS)', 'tab:blue'),
        (ax3, 'meminfo', 'Memory Usage (MB)', 'tab:green')
    ]

    df['state_changed'] = df['state'].ne(df['state'].shift())
    change_points = df[df['state_changed']].copy()

    
    for ax, column, label, color in metrics:
        ax.scatter(change_points['time'], change_points[column], 
                   color='black', s=5, alpha=0.3, zorder=4)

        ax.plot(df['time'], df[column], color=color, linewidth=1.2, alpha=0.8, label=label)
        ax.set_ylabel(label, fontweight='bold')
        ax.grid(True, linestyle='--', alpha=0.4)
        ax.xaxis.set_major_locator(ticker.MaxNLocator(nbins=10))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))

        # 메모리 그래프 추가 처리 (추세선, Private Dirty, GL mtrack)
        if column == 'meminfo':

            # Private Dirty - 실제 점유 메모리 확인용
            if 'private_dirty' in df.columns:
                ax.plot(df['time'], df['private_dirty'], 
                        color='darkorange',
                        linestyle=':',
                        linewidth=1.5,
                        label='Private Dirty')

            # GL mtrack - 그래픽 메모리 누수 구분용
            if 'gl_mtrack' in df.columns:
                ax.plot(df['time'], df['gl_mtrack'],
                        color='purple',
                        linestyle='-.',
                        linewidth=1.3,
                        label='GL mtrack')
                
        
            if len(active_df) > 1:
                time_seconds = (active_df['time'] - active_df['time'].iloc[0]).dt.total_seconds()
                z = np.polyfit(time_seconds, active_df['meminfo'], 1)
                p = np.poly1d(z)

                full_time = (df['time'] - df['time'].iloc[0]).dt.total_seconds()
                ax.plot(df['time'], p(full_time),
                        color='darkred',
                        linewidth=2.5,
                        linestyle='--',
                        label='Leak Trend',
                        alpha=0.7)

            # 추세선이 데이터 범위 밖으로 튀어나가는 거 방지
            ymin, ymax = df[column].min(), df[column].max()
            ax.set_ylim(ymin * 0.9, ymax * 1.2) 
            ax.legend(loc='upper right') 

            # IDLE 구간 회색 배경
            idle_groups = df[df['state'] == 'IDLE_CHECK']
            if not idle_groups.empty:
                for _, group in idle_groups.groupby((idle_groups['time'].diff() > pd.Timedelta(seconds=2)).cumsum()):
                    ax.axvspan(group['time'].min(), group['time'].max(),
                            color='gray', alpha=0.1)

        # 상태 라벨 너무 많으면 겹쳐서 10개당 1개만 표시
        if ax == ax1:
            for i, (_, row) in enumerate(change_points.iterrows()):
                if i % 10 == 0:
                    offset = 15 if (i // 10) % 2 == 0 else -25
                    ax.annotate(row['state'], (row['time'], row[column]),
                                textcoords="offset points", xytext=(0, offset),
                                ha='center', fontsize=8, rotation=45, alpha=0.8)

    oom_status = f"약 {minutes_to_oom:.1f}분 후" if minutes_to_oom != float('inf') else "안정적"
    
    summary_text = (
        f"Memory Leak Analysis\n"
        f"• Leak Rate: {leak_rate_min:.2f} MB/min\n"
        f"• Est. Time to OOM: {oom_status}"
    )

    ax3.text(0.02, 0.95, summary_text, transform=ax3.transAxes, 
             fontsize=10, verticalalignment='top', fontweight='bold',
             bbox=dict(boxstyle='round', facecolor='white', alpha=0.85, edgecolor='gray'))
    
    plt.xlabel('Timeline', fontweight='bold')
    plt.suptitle(
        f"Total Performance Report: {os.path.basename(output_dir)}",
        fontsize=16
    )

    save_path = os.path.join(output_dir, "total_report.png")
    plt.savefig(save_path, bbox_inches='tight', dpi=150)
    plt.close()

    logging.info(f"통합 리포트 저장 완료: {save_path}")