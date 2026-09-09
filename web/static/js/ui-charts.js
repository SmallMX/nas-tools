/* Shared ECharts presentation for the NAS-Tools design tokens. */
(function (window) {
  if (window.NasToolsCharts) return;

  const mounted = new Map();
  const styles = () => getComputedStyle(document.body);
  const token = (name, fallback) => styles().getPropertyValue(name).trim() || fallback;

  function rgb(color) {
    const hex = color.replace("#", "");
    if (/^[0-9a-f]{3}$/i.test(hex)) return Array.from(hex, digit => parseInt(digit + digit, 16));
    if (/^[0-9a-f]{6}$/i.test(hex)) return [0, 2, 4].map(index => parseInt(hex.slice(index, index + 2), 16));
    return (color.match(/[\d.]+/g) || [0, 0, 0]).slice(0, 3).map(Number);
  }

  function blend(from, to, amount) {
    const a = rgb(from);
    const b = rgb(to);
    return `rgb(${a.map((value, index) => Math.round(value + (b[index] - value) * amount)).join(", ")})`;
  }

  function theme() {
    const text = token("--nt-text", "#20332d");
    const muted = token("--nt-muted", "#68786f");
    const border = token("--nt-border", "#dee5dd");
    const surface = token("--nt-surface", "#ffffff");
    const secondary = token("--nt-surface-secondary", "#eef2ec");
    const primary = token("--nt-primary", "#187761");
    const palette = [primary, blend(primary, surface, .28), blend(primary, text, .35),
      blend(primary, surface, .55), blend(muted, primary, .4), blend(primary, surface, .75),
      blend(primary, text, .65), blend(muted, surface, .3)];
    const axis = {
      axisLine: { lineStyle: { color: border } },
      axisTick: { show: false },
      axisLabel: { color: muted, fontSize: 12 },
      nameTextStyle: { color: muted },
      splitLine: { lineStyle: { color: border, type: "dashed" } },
      axisPointer: { lineStyle: { color: muted }, label: { color: text, backgroundColor: secondary } },
    };
    return { text, muted, border, surface, secondary, primary, palette,
      download: blend(primary, surface, .48),
      options: {
        backgroundColor: "transparent",
        color: palette,
        textStyle: { color: text, fontFamily: token("--nt-font", "system-ui"), fontSize: 12 },
        title: { textStyle: { color: text }, subtextStyle: { color: muted } },
        legend: { textStyle: { color: muted }, pageTextStyle: { color: muted }, inactiveColor: border,
          itemWidth: 10, itemHeight: 10, itemGap: 16, icon: "roundRect" },
        tooltip: { backgroundColor: surface, borderColor: border, borderWidth: 1,
          textStyle: { color: text, fontSize: 12 }, padding: [8, 12], confine: true },
        categoryAxis: axis, valueAxis: axis, timeAxis: axis, logAxis: axis,
        toolbox: { iconStyle: { borderColor: muted }, emphasis: { iconStyle: { borderColor: primary } } },
        dataZoom: { backgroundColor: secondary, borderColor: border, fillerColor: blend(primary, surface, .8),
          textStyle: { color: muted }, handleStyle: { color: primary, borderColor: surface } },
        line: { lineStyle: { width: 2 }, symbolSize: 6 },
      },
    };
  }

  const observer = new ResizeObserver(entries => {
    for (const { target } of entries) {
      const chart = mounted.get(target);
      if (chart && !chart.isDisposed() && target.isConnected && target.clientWidth > 0) {
        chart.resize({ width: target.clientWidth });
      }
    }
  });
  // Fragment navigation removes chart containers; release canvases and observers.
  new MutationObserver(() => {
    for (const [element, chart] of mounted) {
      if (!element.isConnected || chart.isDisposed()) {
        observer.unobserve(element);
        mounted.delete(element);
        if (!chart.isDisposed()) chart.dispose();
      }
    }
  }).observe(document.body, { childList: true, subtree: true });

  function create(element, height) {
    const current = echarts.getInstanceByDom(element);
    if (current) current.dispose();
    const chart = echarts.init(element, theme().options, { height, width: element.clientWidth || 320 });
    mounted.set(element, chart);
    observer.observe(element);
    return chart;
  }

  function loading(chart) {
    if (!chart || chart.isDisposed()) return;
    const colors = theme();
    chart.showLoading("default", { text: "正在加载", color: colors.primary,
      textColor: colors.muted, maskColor: colors.surface, spinnerRadius: 8, lineWidth: 2 });
  }

  function donut(dataset, valueKey, label, siteNames = dataset.slice(1).map(row => row[0])) {
    const colors = theme();
    return {
      animation: false,
      color: colors.palette,
      aria: { enabled: true },
      title: { text: dataset.length > 1 ? label : "暂无数据", left: "center", top: "42%", padding: 0,
        textStyle: { fontSize: 14, fontWeight: 500, color: colors.muted } },
      legend: { type: "scroll", bottom: 0, left: "center" },
      tooltip: { trigger: "item", valueFormatter: value => numeral(value).format("0.0 ib") },
      dataset: { source: dataset },
      series: [{ type: "pie", name: label, radius: ["50%", "72%"], center: ["50%", "45%"],
        encode: { itemName: "site", value: valueKey },
        label: { show: false }, labelLine: { show: false },
        itemStyle: { borderColor: colors.surface, borderWidth: 3, borderRadius: 4,
          color: params => colors.palette[Math.max(0, siteNames.indexOf(params.name)) % colors.palette.length] },
        emphasis: { scaleSize: 4 },
        emptyCircleStyle: { color: colors.secondary, borderColor: colors.border, borderWidth: 1 } }],
    };
  }

  window.NasToolsCharts = { theme, create, loading, donut };
})(window);
