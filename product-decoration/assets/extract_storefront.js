// Read-only extractor for known Shopify and SHOPLINE product layouts.
({ source_url, folder_name }) => {
  const shoplineRoot = document.querySelector('theme-product-detail[data-section-type="main-product"]');
  const shopifyInfo = document.querySelector('[id^="ProductInfo-"]');
  const shopifySection = shopifyInfo?.id.slice('ProductInfo-'.length);
  const shopifyTrack = shopifySection && document.getElementById('Slider-Gallery-' + shopifySection);
  const knownShopify = shopifyTrack || shopifyInfo?.matches('product-info');
  const layout = shoplineRoot ? 'shopline-bottle' : knownShopify ? 'shopify-viewkoom' : null;
  const info = shoplineRoot ? shoplineRoot.querySelector('.product-detail__info') ?? shoplineRoot
    : knownShopify ? shopifyInfo : null;
  const shoplineGallery = shoplineRoot?.querySelector('theme-product-media-gallery');
  const track = shoplineRoot ? shoplineGallery?.querySelector('.media-gallery__list') : shopifyTrack;
  const thumbs = shoplineRoot
    ? shoplineGallery?.querySelector('.media-gallery__thumbnail-list')
    : knownShopify && document.getElementById('Slider-Thumbnails-' + shopifySection);
  const descriptions = [...(info?.querySelectorAll(shoplineRoot
    ? '.product-detail__description'
    : '.product__description, .product__info-description') ?? [])];
  const descriptionRoots = descriptions.filter((node) => !descriptions.some((other) => other !== node && other.contains(node)));
  const description = descriptionRoots[0];
  const descriptionSelector = description?.matches('.product__info-description') ? '.product__info-description'
    : description?.matches('.product__description') ? '.product__description'
    : description ? '.product-detail__description' : null;
  const titleElement = info?.querySelector(shoplineRoot ? '.product-detail__title, h1' : 'h1');
  const title = titleElement?.innerText.trim() ?? '';

  const text = (element) => element.innerText.trim();
  const visible = (node) => node.getClientRects().length > 0 && getComputedStyle(node).visibility === 'visible';
  const absoluteMediaUrl = (node, inGallery = false) => {
    if (!node) return null;
    const candidates = [node.getAttribute('data-src'), node.getAttribute('src'),
      node.getAttribute('data-original'), node.querySelector('source[src]')?.getAttribute('src')];
    if (node.tagName === 'IMG' && inGallery) {
      for (const attribute of ['srcset', 'data-srcset']) {
        const largest = (node.getAttribute(attribute) ?? '').match(/[^,\s]+\s+\d+(?:\.\d+)?[wx](?=\s*(?:,|$))/g)
          ?.map((entry) => entry.split(/\s+/)).sort((left, right) => parseFloat(right[1]) - parseFloat(left[1]))[0];
        if (largest) candidates.unshift(largest[0]);
      }
    }
    for (const raw of candidates) {
      if (!raw?.trim() || raw.trim().startsWith('#')) continue;
      try {
        const url = new URL(raw, source_url);
        if (!['http:', 'https:'].includes(url.protocol)) continue;
        if (inGallery && url.pathname.startsWith('/cdn/shop/files/')) url.searchParams.delete('width');
        if ((shoplineRoot || descriptionSelector === '.product__info-description')
            && /^img(?:-[a-z0-9-]+)?\.myshopline\.com$/i.test(url.hostname)) {
          for (const parameter of ['w', 'h', 'q', 'width', 'height', 'quality']) url.searchParams.delete(parameter);
        }
        return url.href;
      } catch {
        continue;
      }
    }
    return null;
  };

  const infoBlocks = [...(info?.children ?? [])];
  const titleIndex = infoBlocks.findIndex((block) => titleElement && block.contains(titleElement));
  const priceIndex = infoBlocks.findIndex((block) => block.matches('[id^="price-"], [id^="main-price-"], .product-page-price'));
  const introBlock = titleIndex < 0 ? null : infoBlocks
    .slice(titleIndex + 1, priceIndex === -1 ? infoBlocks.length : priceIndex)
    .find((block) => block.matches('.rich-text-block') && visible(block));
  const introLines = introBlock ? text(introBlock).split('\n').map((line) => line.trim()).filter(Boolean) : [];
  const intro = introLines.map((line) => {
    const separator = line.indexOf(': ');
    return separator < 0
      ? { heading: line, body: '' }
      : { heading: line.slice(0, separator + 1), body: line.slice(separator + 2) };
  });
  const tags = [...(info?.querySelectorAll('.product-feature-tag') ?? [])]
    .filter(visible).map(text).filter(Boolean);

  const standardOfferRows = [...(info?.querySelectorAll('quantity-breaks label') ?? [])]
    .filter(visible).map(text).filter(Boolean);
  const promotion = [...(info?.querySelectorAll('.product__info-item') ?? [])]
    .find((block) => visible(block) && /Promotion Ends Soon/i.test(text(block)));
  const promotionRows = promotion ? text(promotion).split('\n').map((line) => line.trim()).filter((line) => /^Buy\b/i.test(line)) : [];
  const offerRows = standardOfferRows.length ? standardOfferRows : promotionRows;
  const quantity_discounts = offerRows.flatMap((labelText) => {
    const quantity = labelText.match(/\bBuy\s*(\d+)\b/i);
    if (!quantity) return [];
    const discount = labelText.match(/\bSave\s*(\d+(?:\.\d+)?%)/i);
    return [discount
      ? { quantity: Number(quantity[1]), discount: discount[1] }
      : { quantity: Number(quantity[1]) }];
  });

  const slides = [...(track?.children ?? [])];
  const gallery = slides.map((slide) => {
    const video = absoluteMediaUrl(slide.querySelector('video'), true);
    if (video) return { url: video };
    if (slide.matches('[data-media-type="video"], [data-media-type="external_video"]')
        || slide.querySelector('video, iframe')) return null;
    const image = absoluteMediaUrl(slide.querySelector('img'), true);
    return image ? { url: image } : null;
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
  if (description) collect(description);

  const thumbItems = [...(thumbs?.children ?? [])];
  const thumbMatch = thumbs ? slides.length === thumbItems.length && slides.every((slide, index) => {
    const id = slide.getAttribute('data-media-id');
    return id && id === (thumbItems[index].getAttribute(shoplineRoot ? 'data-media-id' : 'data-target'));
  }) : null;
  const detailMedia = [...(description?.querySelectorAll('img,video') ?? [])]
    .filter((node) => !node.closest('[hidden]')).map((node) => absoluteMediaUrl(node)).filter(Boolean);
  const collectedMedia = details.filter((block) => block.url).map((block) => block.url);
  const detailMediaMatch = detailMedia.length === collectedMedia.length
    && detailMedia.every((url, index) => url === collectedMedia[index]);
  const advertisedMediaTotal = Number(shoplineGallery?.getAttribute('data-media-total') ?? 0);
  const galleryComplete = gallery.length > 0 && gallery.length === slides.length
    && (shoplineRoot ? thumbMatch !== false : thumbMatch === true)
    && (!advertisedMediaTotal || advertisedMediaTotal === slides.length);
  const field = (complete, evidence) => ({ status: complete ? 'captured' : 'needs_review', evidence });
  return {
    source_url, folder_name, title, intro, tags, quantity_discounts, gallery, details,
    audit: {
      layout,
      fields: {
        title: field(Boolean(title), titleElement ? '主商品区标题' : '未定位主商品标题'),
        intro: field(intro.length > 0, introBlock ? '标题与价格之间的 .rich-text-block' : '核对标题下是否有独立简介'),
        tags: field(tags.length > 0, tags.length ? '主商品区可见 .product-feature-tag' : '核对主商品区是否有可见标签'),
        quantity_discounts: field(offerRows.length > 0 && quantity_discounts.length === offerRows.length,
          offerRows.length ? `提取 ${quantity_discounts.length}/${offerRows.length} 个优惠档位` : '核对主商品区是否有可见多件优惠'),
        gallery: field(galleryComplete, `提取 ${gallery.length}/${slides.length} 个主轮播项`),
        details: field(details.length > 0 && descriptionRoots.length === 1 && detailMediaMatch && !unsupportedEmbeds.length,
          descriptionSelector ? `${descriptionSelector}，找到 ${descriptionRoots.length} 个详情容器` : '未定位商品详情容器'),
      },
      introLines,
      slideCount: slides.length,
      thumbCount: thumbItems.length,
      thumbMatch,
      detailMedia,
      detailMediaMatch,
      unsupportedEmbeds,
    },
  };
};
