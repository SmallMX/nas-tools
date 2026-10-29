// Light DOM components share one stylesheet; all rules belong to the media UI.
if (!document.getElementById("nt-media-styles")) {
  const style = document.createElement("style");
  style.id = "nt-media-styles";
  style.textContent = `
    normal-card, normal-card-placeholder, person-card, custom-slide, page-discovery, page-person, page-mediainfo, discovery-navigation, discovery-filters { display: block; min-width: 0; }
    .nt-media-card { position: relative; min-width: 0; color: var(--nt-text, #20332d); }
    .nt-media-card__link { display: block; color: inherit; text-decoration: none; border-radius: 12px; }
    .nt-media-card__link:hover { color: var(--nt-primary, #187761); text-decoration: none; }
    .nt-media-card__poster { position: relative; aspect-ratio: 2 / 3; overflow: hidden; border-radius: 12px; background: var(--nt-primary-soft, #e7f2eb); border: 1px solid var(--nt-border, #dee5dd); }
    .nt-media-card__poster > img { display: block; width: 100%; height: 100%; object-fit: cover; }
    .nt-media-card__poster > .nt-media-skeleton { position: absolute; inset: 0; }
    .nt-media-card__badge { position: absolute; top: 8px; left: 8px; max-width: calc(100% - 64px); padding: 4px 6px; border-radius: 6px; color: #fff; background: rgba(20, 53, 43, .87); font-size: 11px; font-weight: 600; }
    .nt-media-card__rating { left: auto; right: 8px; max-width: none; background: #946518; font-variant-numeric: tabular-nums; }
    .nt-media-card__summary { position: absolute; inset: auto 0 0; padding: 32px 12px 12px; color: #fff; background: linear-gradient(transparent, rgba(11, 33, 26, .94)); opacity: 0; transition: opacity .18s ease; pointer-events: none; }
    .nt-media-card__summary p { margin: 0; font-size: 12px; line-height: 1.65; display: -webkit-box; -webkit-line-clamp: 5; -webkit-box-orient: vertical; overflow: hidden; }
    .nt-media-card__link:hover .nt-media-card__summary, .nt-media-card__link:focus-visible .nt-media-card__summary { opacity: 1; }
    .nt-media-card__title { margin: 8px 0 4px; font-size: 14px; font-weight: 600; line-height: 1.5; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .nt-media-card__meta { color: var(--nt-muted, #68786f); font-size: 12px; line-height: 1.5; min-height: 18px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .nt-media-card__footer { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 8px; }
    .nt-media-card__search { border: 0; background: transparent; color: var(--nt-primary, #187761); padding: 4px 0; font-size: 12px; font-weight: 600; }
    .nt-media-card__search svg { width: 14px; height: 14px; margin-right: 4px; }
    .nt-media-skeleton { border-radius: 12px; background: var(--nt-primary-soft, #e7f2eb); }
    .nt-media-skeleton--poster { aspect-ratio: 2 / 3; }
    .nt-media-skeleton--line { height: 14px; margin-top: 12px; width: 78%; border-radius: 4px; }
    .nt-media-skeleton--short { margin-top: 8px; width: 48%; }
    .nt-media-loading { opacity: .65; }
    .nt-person-card { display: flex; flex-direction: column; align-items: center; width: 100%; min-height: 248px; padding: 24px 16px; border: 1px solid var(--nt-border, #dee5dd); border-radius: 12px; color: var(--nt-text, #20332d); background: var(--nt-surface, #fff); text-align: center; }
    .nt-person-card:hover:not(:disabled) { border-color: var(--nt-primary, #187761); background: var(--nt-primary-soft, #e7f2eb); }
    .nt-person-card:disabled { cursor: default; }
    .nt-person-card__portrait { display: block; width: 104px; height: 104px; border-radius: 50%; overflow: hidden; background: var(--nt-primary-soft, #e7f2eb); }
    .nt-person-card__name { margin: 16px 0 4px; font-size: 14px; line-height: 1.5; font-weight: 600; }
    .nt-person-card__role { color: var(--nt-muted, #68786f); font-size: 12px; line-height: 1.5; }
    .nt-person-card__name, .nt-person-card__role { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
    .nt-slide { margin: 24px 0 32px; min-width: 0; }
    .nt-slide__header { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 12px; }
    .nt-slide__title { margin: 0; font-size: 18px; font-weight: 650; line-height: 1.5; color: var(--nt-text, #20332d); }
    .nt-slide__actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
    .nt-slide__more { border: 0; background: none; padding: 8px; color: var(--nt-primary, #187761); font-size: 12px; font-weight: 600; }
    .nt-slide__arrow { width: 32px; height: 32px; border: 1px solid var(--nt-border, #dee5dd); border-radius: 8px; background: var(--nt-surface, #fff); color: var(--nt-text, #20332d); }
    .nt-slide__arrow:disabled { opacity: .4; }
    .nt-slide__viewport { overflow-x: auto; overscroll-behavior-x: contain; scrollbar-width: thin; scrollbar-color: var(--nt-border, #dee5dd) transparent; padding: 4px 0 12px; }
    .nt-slide__track { display: flex; gap: 16px; align-items: stretch; }
    .nt-slide__track > * { flex: 0 0 176px; width: 176px; min-width: 0; }
    .nt-media-state { grid-column: 1 / -1; padding: 32px 24px; text-align: center; border: 1px dashed var(--nt-border, #dee5dd); border-radius: 12px; background: var(--nt-surface, #fff); color: var(--nt-muted, #68786f); }
    .nt-media-state h2, .nt-media-state h3 { color: var(--nt-text, #20332d); font-size: 18px; margin: 0 0 8px; }
    .nt-media-state p { margin: 0 0 16px; }
    .nt-media-state p:last-child { margin-bottom: 0; }
    .nt-discovery-header { padding-top: 24px; margin-bottom: 24px; }
    .nt-discovery-eyebrow { margin-bottom: 8px; color: var(--nt-muted, #68786f); font-size: 11px; letter-spacing: .08em; font-weight: 600; }
    .nt-discovery-title { margin: 0 0 8px; color: var(--nt-text, #20332d); font-size: 28px; line-height: 1.3; font-weight: 700; }
    .nt-discovery-description { margin: 0; color: var(--nt-muted, #68786f); font-size: 14px; line-height: 1.7; }
    .nt-discovery-banner { display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 24px; border: 1px solid var(--nt-border, #dee5dd); border-radius: 12px; background: var(--nt-primary-soft, #e7f2eb); }
    .nt-discovery-banner h2 { margin: 0 0 4px; font-size: 16px; color: var(--nt-text, #20332d); }
    .nt-discovery-banner p { margin: 0; color: var(--nt-muted, #68786f); font-size: 12px; line-height: 1.7; }
    .nt-discovery-banner__actions { display: flex; gap: 12px; flex-shrink: 0; }
    .nt-discovery-week { display: flex; gap: 8px; flex-wrap: wrap; margin: 24px 0; }
    .nt-discovery-week button { padding: 8px 16px; border: 1px solid var(--nt-border, #dee5dd); border-radius: 8px; background: var(--nt-surface, #fff); color: var(--nt-text, #20332d); }
    .nt-discovery-week button[aria-current="date"] { color: #fff; background: var(--nt-primary, #187761); border-color: var(--nt-primary, #187761); }
    .nt-explore-page { padding-top: var(--nt-space-4); }
    .nt-explore-sources { display: flex; align-items: center; gap: var(--nt-space-6); overflow-x: auto; overscroll-behavior-x: contain; scrollbar-width: thin; border-bottom: 1px solid var(--nt-border); }
    .nt-explore-source { flex: 0 0 auto; min-height: 44px; display: inline-flex; align-items: center; padding: var(--nt-space-3) var(--nt-space-1); border-bottom: 2px solid transparent; color: var(--nt-muted); font-weight: 600; text-decoration: none; white-space: nowrap; }
    .nt-explore-source:hover { color: var(--nt-primary); text-decoration: none; }
    .nt-explore-source[aria-current="page"] { color: var(--nt-primary); border-bottom-color: var(--nt-primary); }
    .nt-explore-filters { padding: var(--nt-space-4) 0; margin-bottom: var(--nt-space-4); border-bottom: 1px solid var(--nt-border); }
    .nt-explore-filter-row { display: flex; align-items: flex-start; gap: var(--nt-space-4); padding: var(--nt-space-1) 0; min-width: 0; }
    .nt-explore-filter-label { flex: 0 0 56px; padding: var(--nt-space-2) 0; color: var(--nt-muted); line-height: 20px; font-size: 14px; }
    .nt-explore-filter-options { display: flex; flex-wrap: wrap; align-items: center; gap: var(--nt-space-1) var(--nt-space-2); min-width: 0; flex: 1; }
    .nt-explore-chip { display: inline-flex; align-items: center; flex: 0 0 auto; border: 1px solid transparent; border-radius: 8px; background: transparent; color: var(--nt-text); font-size: 14px; line-height: 20px; min-height: 36px; padding: var(--nt-space-2) var(--nt-space-3); white-space: nowrap; }
    .nt-explore-chip__check { width: 14px; height: 14px; margin-right: var(--nt-space-1); }
    .nt-explore-chip:hover { color: var(--nt-primary); background: var(--nt-primary-soft); }
    .nt-explore-chip[aria-pressed="true"], .nt-explore-chip[aria-current="date"] { color: var(--nt-primary); background: var(--nt-primary-soft); font-weight: 600; }
    .nt-explore-filter-status { display: flex; align-items: center; flex-wrap: wrap; gap: var(--nt-space-3); margin: var(--nt-space-2) 0 0; color: var(--nt-muted); font-size: 12px; }
    .nt-explore-body.page-body { margin-top: 0; }
    .nt-explore-body .grid-media-card { grid-template-columns: repeat(auto-fill, minmax(144px, 1fr)); gap: var(--nt-space-4) !important; }
    .nt-explore-source:focus-visible, .nt-explore-chip:focus-visible { outline: 2px solid var(--nt-primary); outline-offset: 2px; }
    .nt-media-detail { padding-top: 24px; padding-bottom: 32px; }
    .nt-media-detail__hero { position: relative; overflow: hidden; border: 1px solid var(--nt-border, #dee5dd); border-radius: 12px; background: var(--nt-primary-soft, #e7f2eb); }
    .nt-media-detail__backdrop { position: absolute; inset: 0; opacity: .09; pointer-events: none; }
    .nt-media-detail__backdrop custom-img, .nt-media-detail__backdrop custom-img > div { display: block; width: 100%; height: 100%; }
    .nt-media-detail__hero-content { position: relative; display: flex; align-items: center; gap: 32px; padding: 32px; }
    .nt-media-detail__poster { flex: 0 0 184px; width: 184px; }
    .nt-media-detail__poster img { border-radius: 12px; }
    .nt-media-detail__heading { flex: 1; min-width: 0; }
    .nt-media-detail__heading h1 { color: var(--nt-text, #20332d); font-size: 28px; line-height: 1.35; font-weight: 700; margin: 0 0 12px; }
    .nt-media-detail__year { color: var(--nt-muted, #68786f); font-weight: 400; }
    .nt-media-detail__metadata { display: flex; flex-wrap: wrap; gap: 8px 16px; margin-bottom: 16px; color: var(--nt-muted, #68786f); }
    .nt-media-detail__score { color: #fff; background: #946518; padding: 2px 8px; border-radius: 6px; font-size: 12px; font-weight: 600; }
    .nt-media-detail__links { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 24px; }
    .nt-media-detail__links a { padding: 4px 8px; border: 1px solid var(--nt-border, #dee5dd); border-radius: 6px; color: var(--nt-primary, #187761); background: var(--nt-surface, #fff); font-size: 12px; }
    .nt-media-detail__columns { display: grid; grid-template-columns: minmax(0, 2fr) minmax(240px, 1fr); gap: 24px; margin: 24px 0; }
    .nt-media-detail__section { padding: 24px; border: 1px solid var(--nt-border, #dee5dd); border-radius: 12px; background: var(--nt-surface, #fff); }
    .nt-media-detail__section h2 { margin: 0 0 16px; font-size: 18px; font-weight: 650; }
    .nt-media-detail__overview { margin: 0; line-height: 1.85; color: var(--nt-muted, #68786f); white-space: pre-line; }
    .nt-media-detail__crew { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 16px; margin: 24px 0 0; }
    .nt-media-detail__crew dt { margin-bottom: 4px; font-size: 12px; color: var(--nt-muted, #68786f); }
    .nt-media-detail__crew dd { margin: 0; font-size: 14px; }
    .nt-media-detail__facts { margin: 0; }
    .nt-media-detail__facts > div { display: flex; justify-content: space-between; gap: 16px; padding: 12px 0; border-bottom: 1px solid var(--nt-border, #dee5dd); }
    .nt-media-detail__facts > div:last-child { border-bottom: 0; }
    .nt-media-detail__facts dt { color: var(--nt-muted, #68786f); font-weight: 400; flex-shrink: 0; }
    .nt-media-detail__facts dd { margin: 0; text-align: right; overflow-wrap: anywhere; }
    .nt-media-card__link:focus-visible, .nt-media-card__search:focus-visible, .nt-person-card:focus-visible, .nt-slide button:focus-visible, .nt-slide__viewport:focus-visible, .nt-discovery-week button:focus-visible { outline: 3px solid var(--nt-primary, #187761); outline-offset: 3px; }
    @media (max-width: 767.98px) {
      .nt-explore-sources { gap: var(--nt-space-4); }
      .nt-explore-filter-row { gap: var(--nt-space-2); }
      .nt-explore-filter-label { flex-basis: 40px; padding-top: var(--nt-space-3); }
      .nt-explore-filter-options { flex-wrap: nowrap; overflow-x: auto; overscroll-behavior-x: contain; scrollbar-width: thin; padding-bottom: var(--nt-space-1); }
      .nt-explore-chip { min-height: 44px; }
      .nt-explore-body .grid-media-card { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--nt-space-4) var(--nt-space-3) !important; }
      .nt-slide__track > * { flex-basis: 148px; width: 148px; }
      .nt-discovery-header { padding-top: 16px; }
      .nt-discovery-banner { flex-direction: column; align-items: stretch; padding: 16px; gap: 16px; }
      .nt-discovery-banner__actions > * { flex: 1; }
      .nt-media-detail__hero-content { padding: 24px 16px; gap: 16px; align-items: flex-start; }
      .nt-media-detail__poster { flex-basis: 112px; width: 112px; }
      .nt-media-detail__heading h1 { font-size: 22px; }
      .nt-media-detail__columns { grid-template-columns: 1fr; }
      .nt-media-detail__section { padding: 16px; }
      .nt-media-detail__links { margin-bottom: 16px; }
      .nt-person-card { padding: 16px 12px; min-height: 228px; }
    }
    @media (prefers-reduced-motion: reduce) { .nt-media-card__summary { transition: none; } }
  `;
  document.head.appendChild(style);
}
