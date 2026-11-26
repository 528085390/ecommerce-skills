// Read-only extractor for the Viewkoom product layout used in the verified captures.
({ source_url, folder_name }) => {
  const info = document.querySelector('[id^="ProductInfo-"]');
  const track = document.querySelector('[id^="Slider-Gallery-"]');
  const thumbs = document.querySelector('[id^="Slider-Thumbnails-"]');
  const description = info?.querySelector('.product__description');
  const titleElement = info?.querySelector('h1');
  if (!titleElement || !track || !description) {
    throw new Error('Viewkoom 主商品结构未加载或已变化，请检查主标题、主滑轨和详情容器');
  }

  const text = (element) => element.innerText.trim();
  const absoluteMediaUrl = (node) => {
    const raw = node?.getAttribute('data-src') || node?.getAttribute('src')
      || node?.getAttribute('data-original') || node?.querySelector('source[src]')?.getAttribute('src');
    if (!raw || !raw.trim() || raw.trim().startsWith('#')) return null;
    try {
      const url = new URL(raw, source_url);
      return ['http:', 'https:'].includes(url.protocol) ? url.href : null;
    } catch {
      return null;
    }
  };

  const infoBlocks = [...info.children];
  const priceIndex = infoBlocks.findIndex((block) => block.matches('[id^="price-"], [id^="main-price-"], .product-page-price'));
  const introBlock = infoBlocks.slice(0, priceIndex === -1 ? infoBlocks.length : priceIndex)
    .find((block) => block.matches('.rich-text-block'));
  const introLines = introBlock ? text(introBlock).split('\n').map((line) => line.trim()).filter(Boolean) : [];
  const intro = introLines.map((line) => {
    const separator = line.indexOf(': ');
    return separator < 0
      ? { heading: line, body: '' }
      : { heading: line.slice(0, separator + 1), body: line.slice(separator + 2) };
  });
  const tags = [...info.querySelectorAll('.product-feature-tag')]
    .filter((element) => element.getBoundingClientRect().width > 0).map(text).filter(Boolean);

  const quantity_discounts = [];
  for (const label of info.querySelectorAll('quantity-breaks label')) {
    const labelText = text(label);
    const quantity = labelText.match(/\bBuy\s*(\d+)/i);
    if (!quantity) continue;
    const discount = labelText.match(/\bSave\s*(\d+(?:\.\d+)?%)/i);
    quantity_discounts.push(discount
      ? { quantity: Number(quantity[1]), discount: discount[1] }
      : { quantity: Number(quantity[1]) });
  }

  const slides = [...track.children];
  const gallery = slides.map((slide) => {
    const video = absoluteMediaUrl(slide.querySelector('video'));
    const image = absoluteMediaUrl(slide.querySelector('img'));
    if (video) return { url: video };
    if (!image) return null;
    const url = new URL(image);
    if (url.pathname.startsWith('/cdn/shop/files/')) url.searchParams.delete('width');
    return { url: url.href };
  }).filter(Boolean);

  const details = [];
  const unsupportedEmbeds = [];
  function collect(node) {
    if (node.nodeType === 3) {
      const content = node.textContent.trim();
      if (content) details.push({ type: 'text', text: content });
      return;
    }
    if (node.nodeType !== 1 || node.hasAttribute('hidden')) return;
    const tag = node.tagName;
    if (['STYLE', 'SCRIPT', 'META', 'NOSCRIPT', 'TEMPLATE'].includes(tag)) return;
    if (['IMG', 'VIDEO', 'IFRAME'].includes(tag)) {
      const url = absoluteMediaUrl(node);
      if (!url) return;
      if (tag === 'IFRAME') {
        unsupportedEmbeds.push(url);
        return;
      }
      const type = tag === 'VIDEO' ? 'video' : /\.gif(?:\?|$)/i.test(url) ? 'gif' : 'image';
      details.push({ type, url });
      return;
    }
    if (/^H[1-6]$/.test(tag) && !node.querySelector('img,video,iframe')) {
      if (text(node)) details.push({ type: 'heading', level: Number(tag[1]), text: text(node) });
      return;
    }
    if (['UL', 'OL'].includes(tag) && !node.querySelector('img,video,iframe,li ul,li ol')) {
      const items = [...node.children].filter((element) => element.tagName === 'LI').map(text).filter(Boolean);
      if (items.length) details.push({ type: 'list', items, ordered: tag === 'OL' });
      return;
    }
    if (!node.querySelector('div,p,section,article,ul,ol,h1,h2,h3,h4,h5,h6,img,video,iframe')) {
      if (text(node)) details.push({ type: 'text', text: text(node) });
      return;
    }
    for (const child of node.childNodes) collect(child);
  }
  collect(description);

  const thumbItems = thumbs ? [...thumbs.children] : [];
  const detailMedia = [...description.querySelectorAll('img,video')]
    .filter((node) => !node.closest('[hidden]')).map(absoluteMediaUrl).filter(Boolean);
  const collectedMedia = details.filter((block) => block.url).map((block) => block.url);
  return {
    source_url, folder_name, title: text(titleElement), intro, tags, quantity_discounts, gallery, details,
    audit: {
      introLines,
      slideCount: slides.length,
      thumbCount: thumbItems.length,
      thumbMatch: slides.length === thumbItems.length && slides.every((slide, i) => {
        const id = slide.getAttribute('data-media-id');
        return id && id === thumbItems[i].getAttribute('data-target');
      }),
      detailMedia,
      detailMediaMatch: detailMedia.length === collectedMedia.length
        && detailMedia.every((url, i) => url === collectedMedia[i]),
      unsupportedEmbeds,
    },
  };
};
