import { Component, OnInit } from '@angular/core';
import { BackendService } from '../../_service/backend.service';
import { ActivatedRoute } from '../../../../node_modules/@angular/router';
import { PagingService } from '../../_service/paging.service';

@Component({
  selector: 'app-rapid-ept',
  templateUrl: './rapid-ept.component.html',
  styleUrls: ['./rapid-ept.component.css']
})
export class RapidEptComponent implements OnInit {
  rows:any ;
  loading:any;
  sorts=[]
  constructor(private backendService:BackendService, private activatedRoute:ActivatedRoute, public pagingService:PagingService) {

   }

  ngOnInit() {
    this.activatedRoute.parent.paramMap.subscribe(params => {
      const fabricName = params.get('fabric');
      this.pagingService.fabricName = fabricName ;
      if (fabricName != null) {
         this.getRapidEndpoints() ;
      }
  });
    
  }

  

  getRapidEndpoints() {
    this.backendService.getFilteredEndpoints(this.pagingService.fabricName, this.sorts, false,false,false,false,'rapid',this.pagingService.pageOffset,this.pagingService.pageSize).subscribe(
      (data) => {
          this.pagingService.count = data['count'];
          this.rows = data['objects'];
          this.loading = false;
      }, (error) => {
          this.loading = false;
      }
  );
  }

  setPage(event) {
    this.pagingService.pageOffset = event.offset;
    this.getRapidEndpoints() ;
}

onSort(event) {
    this.sorts = event.sorts;
    this.getRapidEndpoints() ;
}
  

}
